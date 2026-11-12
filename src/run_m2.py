"""run_m2.py – Punkt wejścia dla Milestone 2.

Uruchamia pełną symulację z:
  - modelem popytu (DemandModel),
  - kolejkami rozładunkowymi w hubach (HUB_UNLOAD_DOCKS),
  - losowymi incydentami drogowymi i zamknięciami przejść (stochastic),
  - awariami pojazdów,
  - pełnym pipeline'em analitycznym (Reporter).

Użycie (przykłady):
  python src/run_m2.py                              # domyślnie marzec 2024
  python src/run_m2.py --month 2023-11 --seed 7
  python src/run_m2.py --no-stochastic              # bez losowych zakłóceń
  python src/run_m2.py --no-damage                  # bez zniszczeń UNOSAT
  python src/run_m2.py --block-main "5 08:00" --block-hours 12
  python src/run_m2.py --scenario B                 # scenariusz z briefu (patrz niżej)
  python src/run_m2.py --multi-seed 10              # 10 przebiegów, tabela wyników

Scenariusze (--scenario):
  A  Baseline – domyślne parametry
  B  Skrócenie czasu odprawy o 50%
  C  Blokada Salah al-Din Road (odcięcie głównej arterii)
  D  Decentralizacja magazynów (podwójne zasoby hubów)
"""

import argparse
import copy

import numpy as np
import pandas as pd

import config
import damage
import data
import events as ev
import network
import router as router_mod
import sim_m2
import stochastic
import demand as demand_mod
import analytics


def apply_scenario(scenario: str, cfg_overrides: dict):
    """Nadpisuje parametry config zgodnie z wybranym scenariuszem."""
    if scenario == "A":
        pass  # baseline

    elif scenario == "B":
        # Skrócenie czasu odprawy o 50%
        cfg_overrides["SERVICE_MEAN_MIN"] = config.SERVICE_MEAN_MIN * 0.5
        cfg_overrides["CLEARANCE_MIN"] = (
            config.CLEARANCE_MIN[0] * 0.5,
            config.CLEARANCE_MIN[1] * 0.5,
        )
        print("Scenariusz B: czas odprawy skrócony o 50%")

    elif scenario == "C":
        print("Scenariusz C: blokada głównej arterii (parametr --block-main zostanie ustawiony)")

    elif scenario == "D":
        # Podwójna liczba doków we wszystkich hubach
        for h in sim_m2.HUB_UNLOAD_DOCKS:
            sim_m2.HUB_UNLOAD_DOCKS[h] *= 2
        print("Scenariusz D: decentralizacja – podwójne zasoby rozładunkowe hubów")

    else:
        raise ValueError(f"Nieznany scenariusz: {scenario}. Dostępne: A, B, C, D")


def run_once(args, seed: int) -> tuple[pd.DataFrame, dict, object]:
    """Jeden przebieg symulacji. Zwraca (truck_log, edge_usage, demand_model)."""
    rng = np.random.default_rng(seed)

    # --- dane ---
    trucks, shares = data.prepare(args.month)
    month_start = pd.Timestamp(f"{args.month}-01", tz="UTC")
    next_month = month_start + pd.offsets.MonthBegin(1)
    month_days = (next_month - month_start).days

    # --- graf ---
    G = network.load_graph()
    crossing_nodes = network.snap_points(G, config.CROSSINGS)
    hub_nodes = network.snap_points(G, config.HUBS)

    # --- zniszczenia ---
    damage.set_base_weights(G)
    dm_road, wave_events = None, []
    if config.USE_DAMAGE and not args.no_damage:
        gdf = damage.load_unosat()
        dm_road = damage.DamageModel(G, damage.filter_as_of(gdf, month_start.strftime("%Y-%m-%d")))
        wave_events = ev.unosat_wave_events(dm_road, gdf, month_start, next_month)
        print(f"Fale UNOSAT: {len(wave_events)}")

    # --- router ---
    router = router_mod.FieldRouter(G, hub_nodes, next(iter(crossing_nodes.values())))
    routes = network.compute_routes(G, crossing_nodes, hub_nodes, router)

    # --- zdarzenia: fale UNOSAT + blokady + incydenty stochastyczne ---
    all_events = list(wave_events)

    if args.block_main:
        day_str, clock = args.block_main.split()
        hh, mm = clock.split(":")
        minute = (int(day_str) - 1) * 1440 + int(hh) * 60 + int(mm)
        counts = trucks["crossing"].value_counts()
        weights = {
            (c, h): counts.get(c, 0) * float(shares.get(h, 0))
            for c in crossing_nodes for h in shares.columns
        }
        for (u, v), n_trucks in ev.busiest_edges(routes, weights, args.block_k):
            all_events += ev.blockade_events(
                G, minute, args.block_hours, [(u, v)],
                f"scenariusz C – główna arteria ({n_trucks:.0f} ciężarówek)"
            )

    if not args.no_stochastic:
        # Losowe incydenty drogowe
        busy = ev.busiest_edges(routes, {
            (c, h): trucks["crossing"].value_counts().get(c, 0)
            for c in crossing_nodes for h in hub_nodes
        }, k=len(G.edges()))
        all_events += stochastic.generate_road_incidents(G, month_days, rng, busy_edges=busy)
        all_events += stochastic.generate_crossing_closures(crossing_nodes, month_days, rng)
        # Wyczyść stan globalny zamkniętych przejść (ważne przy multi-seed)
        stochastic.CLOSED_CROSSINGS.clear()
        print(f"Zdarzenia stochastyczne: {sum(1 for e in all_events if 'INCYDENT' in e.label or 'ZAMKNIĘCIE' in e.label)}")

    # --- model popytu ---
    dm_demand = demand_mod.DemandModel()

    # --- symulacja ---
    trace: list = []
    log, edge_usage = sim_m2.run_simulation(
        trucks=trucks,
        G=G,
        router=router,
        crossing_nodes=crossing_nodes,
        hub_nodes=hub_nodes,
        hub_shares=shares,
        demand_model=dm_demand,
        events=all_events,
        damage_model=dm_road,
        month=args.month,
        rng=rng,
        trace_every=getattr(args, "log_every", 0),
        trace_days=sim_m2.parse_days(getattr(args, "log_days", "")),
        trace_lines=trace,
    )

    return log, edge_usage, dm_demand, routes, G, trace


def summarize_m2(log: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tabele podsumowań kompatybilne z M1 + nowe kolumny M2."""
    q = log.groupby("crossing").agg(
        trucks=("truck_id", "size"),
        queue_mean_min=("queue_min", "mean"),
        queue_p95_min=("queue_min", lambda s: s.quantile(0.95)),
        queue_max_min=("queue_min", "max"),
        unload_wait_mean_min=("unload_wait_min", "mean"),
        breakdown_pct=("breakdown_delay_min", lambda s: (s > 0).mean() * 100),
    )
    h = log[log["delivered"]].groupby("hub").agg(
        trucks=("truck_id", "size"),
        route_km_mean=("route_km", "mean"),
        travel_min_mean=("travel_min", "mean"),
        travel_min_p95=("travel_min", lambda s: s.quantile(0.95)),
        unload_wait_mean_min=("unload_wait_min", "mean"),
        cargo_mt_total=("cargo_mt", "sum"),
    )
    return q.round(1), h.round(1)


def main():
    ap = argparse.ArgumentParser(description="GH-LR Simulator – Milestone 2")
    ap.add_argument("--month", default=config.MONTH)
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--scenario", default="A", choices=["A", "B", "C", "D"])
    ap.add_argument("--no-damage", action="store_true")
    ap.add_argument("--no-stochastic", action="store_true", help="Wyłącz losowe zakłócenia")
    ap.add_argument("--block-main", default="")
    ap.add_argument("--block-hours", type=float, default=config.BLOCK_HOURS)
    ap.add_argument("--block-k", type=int, default=1)
    ap.add_argument("--multi-seed", type=int, default=0,
                    help="Uruchom N razy z różnymi seedami i agreguj wyniki")
    ap.add_argument("--log-every", type=int, default=0)
    ap.add_argument("--log-days", default="")
    a = ap.parse_args()

    # Nadpisz parametry config zgodnie ze scenariuszem
    cfg_overrides: dict = {}
    apply_scenario(a.scenario, cfg_overrides)
    for attr, val in cfg_overrides.items():
        setattr(config, attr, val)

    outdir = config.OUTPUT / a.month / f"scenario_{a.scenario}"

    # --- Tryb multi-seed ---
    if a.multi_seed > 1:
        all_logs = []
        all_demands = []
        print(f"Multi-seed: {a.multi_seed} przebiegów scenariusza {a.scenario}...")
        for i in range(a.multi_seed):
            seed_i = a.seed + i
            log_i, _, dm_i, _, _, _ = run_once(a, seed=seed_i)
            log_i["seed"] = seed_i
            all_logs.append(log_i)
            all_demands.append(dm_i.summary().assign(seed=seed_i))
            print(f"  seed {seed_i}: dowiezionych {log_i['delivered'].sum()}/{len(log_i)}")

        combined = pd.concat(all_logs, ignore_index=True)
        outdir.mkdir(parents=True, exist_ok=True)
        combined.to_csv(outdir / "multiseed_truck_log.csv", index=False)

        # Tabela agregacji KPI przez seedy
        agg = combined.groupby("seed").agg(
            delivered_pct=("delivered", lambda s: round(100 * s.mean(), 1)),
            queue_mean=("queue_min", "mean"),
            travel_mean=("travel_min", "mean"),
            stuck_trucks=("stuck_min", lambda s: (s > 0).sum()),
        ).round(1)
        agg.to_csv(outdir / "multiseed_kpi.csv")
        print("\nAgregacja multi-seed:")
        print(agg.to_string())
        print(f"\nWyniki w {outdir}/")
        return

    # --- Pojedynczy przebieg ---
    log, edge_usage, dm_demand, routes, G, trace = run_once(a, seed=a.seed)

    outdir.mkdir(parents=True, exist_ok=True)
    log.to_csv(outdir / "truck_log.csv", index=False)
    if trace:
        trace.sort(key=lambda s: s[1:13])
        (outdir / "sim_log.txt").write_text("\n".join(trace), encoding="utf-8")

    q, h = summarize_m2(log)
    q.to_csv(outdir / "summary_crossings.csv")
    h.to_csv(outdir / "summary_hubs.csv")

    print("\nPrzejścia:\n", q.to_string())
    print("\nHuby:\n", h.to_string())
    print(f"\nZdarzenia: {len([e for e in [] if True])}; "
          f"ciężarówek ze zmianą trasy: {(log['replans'] > 0).sum()}; "
          f"awarie pojazdów: {(log['breakdown_delay_min'] > 0).sum()}; "
          f"niedowiezionych: {(~log['delivered']).sum()}")

    # --- analityka ---
    reporter = analytics.Reporter(outdir, a.month)
    reporter.run(
        truck_log=log,
        demand_model=dm_demand,
        hub_edge_usage=edge_usage,
        G=G,
    )

    print(f"\nGotowe. Wyniki w {outdir}/")


if __name__ == "__main__":
    main()
