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
"""
import argparse

import pandas as pd

import config
import damage
import data
import events as ev
import network
import router as router_mod
import sim


def summarize(log):
    """Dwie tabele: kolejki na przejściach i czasy dojazdu do hubów (tylko dowiezione ciężarówki)."""
    q = log.groupby("crossing").agg(
        trucks=("truck_id", "size"), queue_mean_min=("queue_min", "mean"),
        queue_p95_min=("queue_min", lambda s: s.quantile(0.95)), queue_max_min=("queue_min", "max"),
    )
    h = log[log["delivered"]].groupby("hub").agg(
        trucks=("truck_id", "size"), route_km_mean=("route_km", "mean"), travel_min_mean=("travel_min", "mean"),
        travel_min_p95=("travel_min", lambda s: s.quantile(0.95)),
    )
    return q.round(1), h.round(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=config.MONTH)
    ap.add_argument("--prepare-data", action="store_true", help="Excel -> data/processed")
    ap.add_argument("--build-graph", action="store_true", help="pobierz graf z Overpass")
    ap.add_argument("--describe-unosat", action="store_true", help="pokaż kolumny i daty UNOSAT")
    ap.add_argument("--diagnose", action="store_true", help="diagnostyka grafu, przypięć, tras i zniszczeń (bez symulacji)")
    ap.add_argument("--no-damage", action="store_true", help="bez zniszczeń (punkt odniesienia)")
    ap.add_argument("--block-main", default="", help='zamknij najruchliwsze drogi: "DZIEŃ GG:MM", np. "5 08:00"')
    ap.add_argument("--block-hours", type=float, default=config.BLOCK_HOURS)
    ap.add_argument("--block-k", type=int, default=1, help="ile najruchliwszych dróg zamknąć")
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--log-every", type=int, default=0, help="log tekstowy: co N-ta ciężarówka")
    ap.add_argument("--log-days", default="", help="log tekstowy: wszystkie ciężarówki z dni miesiąca, np. 1,2 albo 3-5")
    a = ap.parse_args()

    if a.prepare_data:
        data.prepare(a.month, force=True)
        return
    if a.build_graph:
        network.build_graph()
        return
    if a.describe_unosat:
        damage.describe_unosat(damage.load_unosat())
        return

    # --- dane ---
    trucks, shares = data.prepare(a.month)
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
        dm = damage.DamageModel(G, damage.filter_as_of(gdf, month_start.strftime("%Y-%m-%d")))
        wave_events = ev.unosat_wave_events(dm, gdf, month_start, next_month)
        print(f"Fale UNOSAT w tym miesiącu: {len(wave_events)}")

    # --- router D* Lite i trasy bazowe ---
    router = router_mod.FieldRouter(G, hub_nodes, next(iter(crossing_nodes.values())))
    routes = network.compute_routes(G, crossing_nodes, hub_nodes, router)
    outdir = config.OUTPUT / a.month
    if a.diagnose:
        import diagnose
        diagnose.report(G, crossing_nodes, hub_nodes, routes, outdir)
        return

    # --- blokady ---
    events = list(wave_events)
    if a.block_main:
        day, clock = a.block_main.split()
        hh, mm = clock.split(":")
        minute = (int(day) - 1) * 1440 + int(hh) * 60 + int(mm)
        counts = trucks["crossing"].value_counts()
        weights = {(c, h): counts.get(c, 0) * float(shares[h]) for c in crossing_nodes for h in shares.index}
        for (u, v), n_trucks in ev.busiest_edges(routes, weights, a.block_k):
            events += ev.blockade_events(G, minute, a.block_hours, [(u, v)],
                                         f"najruchliwsza droga (planowo {n_trucks:.0f} ciężarówek w miesiącu)")

    # --- symulacja ---
    trace = []
    log = sim.run_simulation(trucks, G, router, crossing_nodes, hub_nodes, shares, events=events,
                             damage_model=dm, month=a.month, seed=a.seed, trace_every=a.log_every,
                             trace_days=sim.parse_days(a.log_days), trace_lines=trace)

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
    print(f"\nZdarzenia: {len(events)}; ciężarówek ze zmianą trasy: {(log['replans'] > 0).sum()}; "
          f"czekało bez drogi: {(log['stuck_min'] > 0).sum()} (łącznie {log['stuck_min'].sum():.0f} min); "
          f"niedowiezionych: {(~log['delivered']).sum()}")
    print(f"\nGotowe. Wyniki w {outdir}/ (truck_log.csv, summary_*.csv)")


if __name__ == "__main__":
    main()
