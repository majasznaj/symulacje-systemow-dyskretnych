"""Uruchamianie symulacji.

Kolejność pierwszego razu (np. w Colabie):
  python src/run.py --prepare-data      # Excel -> data/processed
  python src/run.py --build-graph       # graf z Overpass -> data/processed/gaza_drive.graphml (graf jest już w repo)
  python src/run.py --describe-unosat   # diagnostyka kolumn SensorDate
  python src/run.py --diagnose          # graf, przypięcia, trasy, mapa zniszczeń (bez symulacji)
  python src/run.py                     # symulacja (stan zniszczeń z 1. dnia miesiąca + fale UNOSAT w trakcie)
Zdarzenia (opcjonalnie):
  --block-main "5 08:00" --block-hours 12 --block-k 1   # zamknij k najruchliwszych dróg 5. dnia o 08:00
Punkt odniesienia bez zniszczeń: --no-damage

Milestone 2 (domyślnie wyłączone, bez flag wynik jest taki sam jak w M1):
  --unloading     rozładunek w hubie: doki jako zasób SimPy (config.HUB_UNLOAD_DOCKS)
  --demand        popyt na żywność: zapasy hubów, pokrycie zapotrzebowania, uproszczona faza (demand.py)
  --stochastic    losowe incydenty drogowe, zamknięcia przejść i awarie pojazdów (stochastic.py)
  --analytics     tabele KPI i wykresy kpi_*.png (analytics.py)
  --m2            skrót: --unloading --demand --stochastic --analytics
  --scenario A-E  A bazowy, B odprawa o 50% krótsza, C blokada drogi, D podwójna liczba doków, E dwa razy więcej ciężarówek
  --multi-seed N  N przebiegów z kolejnymi ziarnami i tabela wyników (średnia, odchylenie)
"""
import argparse

import numpy as np
import pandas as pd

import config
import damage
import data
import events as ev
import network
import router as router_mod
import sim
import stochastic

SCENARIOS = {
    "A": "bazowy",
    "B": "czas odprawy o 50% krótszy",
    "C": "blokada najruchliwszej drogi",
    "D": "podwójna liczba doków rozładunkowych (decentralizacja magazynów)",
    "E": "dwa razy więcej ciężarówek przy tej samej przepustowości granicy",
}


def summarize(log):
    """Dwie tabele: kolejki na przejściach i czasy dojazdu do hubów (tylko dowiezione ciężarówki)."""
    q = log.groupby("crossing").agg(
        trucks=("truck_id", "size"), queue_mean_min=("queue_min", "mean"),
        queue_p95_min=("queue_min", lambda s: s.quantile(0.95)), queue_max_min=("queue_min", "max"),
    )
    agg = dict(trucks=("truck_id", "size"), route_km_mean=("route_km", "mean"), travel_min_mean=("travel_min", "mean"),
               travel_min_p95=("travel_min", lambda s: s.quantile(0.95)))
    if (log["unload_min"] > 0).any():   # rozładunek włączony
        agg["unload_wait_mean_min"] = ("unload_wait_min", "mean")
    h = log[log["delivered"]].groupby("hub").agg(**agg)
    return q.round(1), h.round(1)


def apply_scenario(a):
    """Ustawia parametry zgodnie ze scenariuszem. Zwraca dwa pola: czy zwiększyć ruch 2x i czy włączyć doki."""
    double_trucks = False
    if a.scenario == "B":
        config.SERVICE_MEAN_MIN *= 0.5
        config.CLEARANCE_MIN = tuple(x * 0.5 for x in config.CLEARANCE_MIN)
    elif a.scenario == "C" and not a.block_main:
        a.block_main = "5 08:00"
    elif a.scenario == "D":
        config.HUB_UNLOAD_DOCKS = {h: 2 * n for h, n in config.HUB_UNLOAD_DOCKS.items()}
        config.DEFAULT_HUB_DOCKS *= 2
        a.unloading = True
    elif a.scenario == "E":
        double_trucks = True
    return double_trucks


def build_world(a, double_trucks=False, quiet=False):
    """Dane, graf, zniszczenia i router D* Lite. Graf jest zmieniany w trakcie symulacji, więc każdy przebieg buduje go od nowa."""
    trucks, shares = data.prepare(a.month)
    if double_trucks:   # scenariusz E: te same przejścia, dwa razy więcej ciężarówek (nowe identyfikatory)
        trucks = pd.concat([trucks, trucks.assign(truck_id=trucks["truck_id"] + 10_000_000)], ignore_index=True)
    month_start = pd.Timestamp(f"{a.month}-01", tz="UTC")
    next_month = month_start + pd.offsets.MonthBegin(1)

    # --- graf ---
    G = network.load_graph()
    crossing_nodes = network.snap_points(G, config.CROSSINGS)
    hub_nodes = network.snap_points(G, config.HUBS)

    # --- zniszczenia: stan na początek miesiąca i fale UNOSAT w trakcie miesiąca ---
    damage.set_base_weights(G)
    dm, wave_events = None, []
    if config.USE_DAMAGE and not a.no_damage:
        gdf = damage.load_unosat()
        dm = damage.DamageModel(
            G, damage.filter_as_of(gdf, month_start.strftime("%Y-%m-%d"), config.DAMAGE_LIFETIME_DAYS))
        wave_events = ev.unosat_wave_events(dm, gdf, month_start, next_month)
        n_add = sum(1 for e in wave_events if e.label.startswith("FALA"))
        n_fix = sum(1 for e in wave_events if e.label.startswith("NAPRAWA"))
        life = config.DAMAGE_LIFETIME_DAYS
        if not quiet:
            print(f"Fale UNOSAT w tym miesiącu: {n_add} wejść, {n_fix} napraw"
                  + (f" (życie {life:g} dni)" if life else " (bez schodzenia)"))

    # --- router D* Lite i trasy bazowe ---
    router = router_mod.FieldRouter(G, hub_nodes, next(iter(crossing_nodes.values())))
    routes = network.compute_routes(G, crossing_nodes, hub_nodes, router)
    return dict(trucks=trucks, shares=shares, G=G, crossing_nodes=crossing_nodes, hub_nodes=hub_nodes, dm=dm,
                wave_events=wave_events, router=router, routes=routes, next_month=next_month,
                month_days=(next_month - month_start).days)


def run_once(a, seed, double_trucks=False, quiet=False):
    """Jeden pełny przebieg. Zwraca (log, edge_usage, demand_model, routes, G, events, trace)."""
    w = build_world(a, double_trucks, quiet)
    trucks, shares, G, router, routes, dm = w["trucks"], w["shares"], w["G"], w["router"], w["routes"], w["dm"]
    crossing_nodes, hub_nodes, month_days = w["crossing_nodes"], w["hub_nodes"], w["month_days"]

    # waga trasy = oczekiwana liczba ciężarówek: wjazdy na przejściu × udział huba P(hub | przejście)
    counts = trucks["crossing"].value_counts()
    weights = {(c, h): counts.get(c, 0) * float(shares.loc[c, h] / shares.loc[c].sum())
               for c in crossing_nodes for h in hub_nodes if c in shares.index}

    # --- blokady ---
    events = list(w["wave_events"])
    if a.block_main:
        day, clock = a.block_main.split()
        hh, mm = clock.split(":")
        minute = (int(day) - 1) * 1440 + int(hh) * 60 + int(mm)
        for (u, v), n_trucks in ev.busiest_edges(routes, weights, a.block_k):
            events += ev.blockade_events(G, minute, a.block_hours, [(u, v)],
                                         f"najruchliwsza droga (planowo {n_trucks:.0f} ciężarówek w miesiącu)")

    # --- zdarzenia losowe (M2) ---
    closed = set()
    if a.stochastic:
        rng_s = np.random.default_rng([seed, 7])
        busy = ev.busiest_edges(routes, weights, k=len(G.edges()))
        events += stochastic.generate_road_incidents(G, month_days, rng_s, busy_edges=busy)
        events += stochastic.generate_crossing_closures(crossing_nodes, month_days, rng_s, closed)
        if not quiet:
            n_st = sum(1 for e in events if e.label.startswith(("INCYDENT", "ZAMKNIĘCIE")))
            print(f"Zdarzenia losowe: {n_st} (incydenty drogowe i zamknięcia przejść)")

    import demand as demand_mod
    demand_model = demand_mod.DemandModel() if a.demand else None
    edge_usage = {} if a.analytics else None

    # --- symulacja ---
    trace = []
    log = sim.run_simulation(
        trucks, G, router, crossing_nodes, hub_nodes, shares, events=events,
        damage_model=dm, month=a.month, seed=seed, trace_every=a.log_every,
        trace_days=sim.parse_days(a.log_days), trace_lines=trace,
        unload_docks=config.HUB_UNLOAD_DOCKS if a.unloading else None,
        demand_model=demand_model, closed_crossings=closed if a.stochastic else None,
        breakdowns=a.stochastic, edge_usage=edge_usage)
    return log, edge_usage, demand_model, routes, G, events, trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=config.MONTH)
    ap.add_argument("--prepare-data", action="store_true", help="Excel -> data/processed")
    ap.add_argument("--build-graph", action="store_true", help="pobierz graf z Overpass")
    ap.add_argument("--describe-unosat", action="store_true", help="pokaż kolumny i daty UNOSAT")
    ap.add_argument("--diagnose", action="store_true", help="diagnostyka grafu, przypięć, tras i zniszczeń (bez symulacji)")
    ap.add_argument("--no-damage", action="store_true", help="bez zniszczeń (punkt odniesienia)")
    ap.add_argument("--damage-lifetime", type=float, default=None,
                    help="po ilu dniach od zdjęcia UNOSAT punkty schodzą z dróg (domyślnie zostają)")
    ap.add_argument("--block-main", default="", help='zamknij najruchliwsze drogi: "DZIEŃ GG:MM", np. "5 08:00"')
    ap.add_argument("--block-hours", type=float, default=config.BLOCK_HOURS)
    ap.add_argument("--block-k", type=int, default=1, help="ile najruchliwszych dróg zamknąć")
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--log-every", type=int, default=0, help="log tekstowy: co N-ta ciężarówka")
    ap.add_argument("--log-days", default="", help="log tekstowy: wszystkie ciężarówki z dni miesiąca, np. 1,2 albo 3-5")
    # Milestone 2
    ap.add_argument("--unloading", action="store_true", help="rozładunek w hubie (doki, config.HUB_UNLOAD_DOCKS)")
    ap.add_argument("--demand", action="store_true", help="popyt na żywność i pokrycie zapotrzebowania w hubach")
    ap.add_argument("--stochastic", action="store_true", help="losowe incydenty, zamknięcia przejść i awarie")
    ap.add_argument("--analytics", action="store_true", help="tabele KPI i wykresy kpi_*.png")
    ap.add_argument("--m2", action="store_true", help="skrót: --unloading --demand --stochastic --analytics")
    ap.add_argument("--scenario", default=None, choices=sorted(SCENARIOS), help="; ".join(f"{k}: {v}" for k, v in SCENARIOS.items()))
    ap.add_argument("--multi-seed", type=int, default=0, help="N przebiegów z ziarnami seed, seed+1, ... i tabela wyników")
    a = ap.parse_args()
    if a.m2:
        a.unloading = a.demand = a.stochastic = a.analytics = True
    if a.damage_lifetime is not None:
        config.DAMAGE_LIFETIME_DAYS = a.damage_lifetime

    if a.prepare_data:
        data.prepare(a.month, force=True)
        return
    if a.build_graph:
        network.build_graph()
        return
    if a.describe_unosat:
        damage.describe_unosat(damage.load_unosat())
        return

    double_trucks = apply_scenario(a) if a.scenario else False
    outdir = config.OUTPUT / a.month / (f"scenario_{a.scenario}" if a.scenario else "")
    if a.scenario:
        print(f"Scenariusz {a.scenario}: {SCENARIOS[a.scenario]}")

    if a.diagnose:
        import diagnose
        w = build_world(a, double_trucks)
        diagnose.report(w["G"], w["crossing_nodes"], w["hub_nodes"], w["routes"], outdir)
        return

    if a.multi_seed > 1:
        multi_seed(a, double_trucks, outdir)
        return

    log, edge_usage, demand_model, routes, G, events, trace = run_once(a, a.seed, double_trucks)

    # --- wyniki ---
    outdir.mkdir(parents=True, exist_ok=True)
    log.to_csv(outdir / "truck_log.csv", index=False)
    q, h = summarize(log)
    q.to_csv(outdir / "summary_crossings.csv")
    h.to_csv(outdir / "summary_hubs.csv")
    if trace:
        trace.sort(key=lambda s: s[1:13])   # chronologicznie ("dz.DD GG:MM")
        (outdir / "sim_log.txt").write_text("\n".join(trace), encoding="utf-8")

    print("\nPrzejścia:\n", q.to_string())
    print("\nHuby:\n", h.to_string())
    causes = log["replan_causes"].fillna("") if "replan_causes" in log else ""
    n_unosat = causes.str.contains("UNOSAT").sum() if len(log) else 0
    print(f"\nZdarzenia: {len(events)}; objazdy w trakcie jazdy: {(log['replans'] > 0).sum()}; "
          f"inna trasa niż 1. dnia miesiąca przez UNOSAT: {n_unosat}; "
          f"czekało bez drogi: {(log['stuck_min'] > 0).sum()} (łącznie {log['stuck_min'].sum():.0f} min); "
          f"niedowiezionych: {(~log['delivered']).sum()}")
    if a.stochastic:
        print(f"Awarie pojazdów: {(log['breakdown_delay_min'] > 0).sum()}")
    if demand_model is not None:
        summary = demand_model.summary()
        summary.to_csv(outdir / "demand_summary.csv", index=False)
        history = demand_model.report()
        if not history.empty:
            history.to_csv(outdir / "demand_history.csv", index=False)
        print("\nPopyt na żywność (pokrycie = zjedzone / zapotrzebowanie):\n", summary.to_string(index=False))
        print(f"Pokrycie łącznie: {demand_model.total_coverage_pct()}%")
    if a.analytics:
        import analytics
        analytics.Reporter(outdir, a.month).run(truck_log=log, demand_model=demand_model,
                                                hub_edge_usage=edge_usage, G=G)
    print(f"\nGotowe. Wyniki w {outdir}/ (truck_log.csv, summary_*.csv)")


def multi_seed(a, double_trucks, outdir):
    """N przebiegów z kolejnymi ziarnami: jedna linia na przebieg i średnia z odchyleniem."""
    rows = []
    for i in range(a.multi_seed):
        seed = a.seed + i
        log, _, dm, _, _, _, _ = run_once(a, seed, double_trucks, quiet=True)
        row = {
            "seed": seed,
            "delivered_pct": round(100 * log["delivered"].mean(), 1),
            "queue_mean_min": round(log["queue_min"].mean(), 1),
            "queue_p95_min": round(log["queue_min"].quantile(0.95), 1),
            "travel_mean_min": round(log.loc[log["delivered"], "travel_min"].mean(), 1),
            "stuck_trucks": int((log["stuck_min"] > 0).sum()),
        }
        if (log["unload_min"] > 0).any():
            row["unload_wait_mean_min"] = round(log.loc[log["delivered"], "unload_wait_min"].mean(), 1)
        if dm is not None:
            row["food_coverage_pct"] = dm.total_coverage_pct()
        rows.append(row)
        print(f"  ziarno {seed}: " + ", ".join(f"{k}={v}" for k, v in row.items() if k != "seed"))
    table = pd.DataFrame(rows).set_index("seed")
    outdir.mkdir(parents=True, exist_ok=True)
    table.to_csv(outdir / "multiseed_kpi.csv")
    agg = table.agg(["mean", "std"]).round(2)
    agg.to_csv(outdir / "multiseed_summary.csv")
    print(f"\nWyniki {a.multi_seed} przebiegów (średnia i odchylenie standardowe):\n", agg.to_string())
    print(f"\nGotowe. Wyniki w {outdir}/ (multiseed_kpi.csv, multiseed_summary.csv)")


if __name__ == "__main__":
    main()
