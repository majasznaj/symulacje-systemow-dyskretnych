"""Uruchamianie symulacji.

Kolejność pierwszego razu (np. w Colabie):
  python src/run.py --prepare-data      # Excel -> data/processed
  python src/run.py --build-graph       # graf z Overpass -> data/processed/gaza_drive.graphml
  python src/run.py --graph-check       # co wycina budowa grafu, gęstość sieci wokół Rafah (Overpass)
  python src/run.py --describe-unosat   # diagnostyka kolumn SensorDate
  python src/run.py --diagnose          # graf, przypięcia, zniszczenia (bez symulacji)
  python src/run.py                     # symulacja (domyślnie z falami UNOSAT w czasie)
Zdarzenia (opcjonalnie):
  --block-main "5 08:00" --block-hours 12 --block-k 1   # zamknij k najruchliwszych dróg 5. dnia o 08:00
  --blockades 3                                         # 3 losowe blokady w miesiącu
Test kodu bez sieci i bez UNOSAT: python src/run.py --toy
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=config.MONTH)
    ap.add_argument("--prepare-data", action="store_true", help="Excel -> data/processed")
    ap.add_argument("--build-graph", action="store_true", help="pobierz graf z Overpass")
    ap.add_argument("--offline", action="store_true", help="z --graph-check: tylko zapisany graf, bez Overpass")
    ap.add_argument("--graph-check", action="store_true", help="diagnostyka surowego grafu OSM (Overpass), bez symulacji")
    ap.add_argument("--describe-unosat", action="store_true", help="pokaż kolumny i daty UNOSAT")
    ap.add_argument("--diagnose", action="store_true", help="diagnostyka grafu, przypięć i zniszczeń (bez symulacji)")
    ap.add_argument("--toy", action="store_true", help="sztuczny graf i zniszczenia (test kodu)")
    ap.add_argument("--no-damage", action="store_true")
    ap.add_argument("--damage-as-of", default=config.DAMAGE_AS_OF,
                    help="stały stan zniszczeń na dzień RRRR-MM-DD, bez fal w czasie")
    ap.add_argument("--no-waves", action="store_true", help="bez fal UNOSAT w trakcie miesiąca")
    ap.add_argument("--block-main", default="", help='zamknij najruchliwsze drogi: "DZIEŃ GG:MM", np. "5 08:00"')
    ap.add_argument("--block-hours", type=float, default=config.BLOCK_HOURS)
    ap.add_argument("--block-k", type=int, default=1, help="ile najruchliwszych dróg zamknąć")
    ap.add_argument("--blockades", type=int, default=0, help="liczba losowych blokad w miesiącu")
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
    if a.graph_check:
        import graphcheck
        graphcheck.run(offline=a.offline)
        return
    if a.describe_unosat:
        damage.describe_unosat(damage.load_unosat())
        return

    # --- dane ---
    trucks, shares = data.prepare(a.month)
    month_start = pd.Timestamp(f"{a.month}-01", tz="UTC")
    next_month = month_start + pd.offsets.MonthBegin(1)
    month_minutes = (next_month - month_start).total_seconds() / 60

    # --- graf ---
    if a.toy:
        import toy
        graph_file = config.DATA_PROC / "toy_graph.graphml"
        toy.make_toy_graph(graph_file)
        G = network.load_graph(graph_file)
    else:
        G = network.load_graph()
    crossing_nodes = network.snap_points(G, config.CROSSINGS)
    hub_nodes = network.snap_points(G, config.HUBS)

    # --- zniszczenia: stan początkowy i (w trybie dynamicznym) fale w trakcie miesiąca ---
    damage.set_base_weights(G)
    dm, wave_events = None, []
    if config.USE_DAMAGE and not a.no_damage:
        gdf = toy.make_toy_damage() if a.toy else damage.load_unosat()
        if a.damage_as_of:   # tryb statyczny
            dm = damage.DamageModel(G, damage.filter_as_of(gdf, a.damage_as_of))
        else:                # tryb dynamiczny
            dm = damage.DamageModel(G, damage.filter_as_of(gdf, month_start.strftime("%Y-%m-%d")))
            if not a.no_waves:
                wave_events = ev.unosat_wave_events(dm, gdf, month_start, next_month)
                print(f"Fale UNOSAT w tym miesiącu: {len(wave_events)}")

    # --- router D* Lite i trasy bazowe ---
    router = router_mod.FieldRouter(G, hub_nodes, next(iter(crossing_nodes.values())))
    routes = network.compute_routes(G, crossing_nodes, hub_nodes, router)
    if a.diagnose:
        import diagnose
        diagnose.report(G, crossing_nodes, hub_nodes, routes, config.OUTPUT / (a.month + ("_toy" if a.toy else "")))
        return

    # --- blokady ---
    events = list(wave_events)
    if a.block_main:
        day, clock = a.block_main.split()
        hh, mm = clock.split(":")
        minute = (int(day) - 1) * 1440 + int(hh) * 60 + int(mm)
        counts = trucks["crossing"].value_counts()
        weights = {(c, h): counts.get(c, 0) * float(shares[h]) for c in crossing_nodes for h in shares.index}
        top = ev.busiest_edges(routes, weights, a.block_k)
        for (u, v), n_trucks in top:
            events += ev.blockade_events(G, minute, a.block_hours, [(u, v)],
                                         f"najruchliwsza droga (planowo {n_trucks:.0f} ciężarówek w miesiącu)")
    if a.blockades:
        events += ev.random_blockades(G, np.random.default_rng(a.seed + 1), a.blockades, month_minutes, routes)

   # --- symulacja i raport ---
    trace = []
    log = sim.run_simulation(trucks, G, router, crossing_nodes, hub_nodes, shares, routes, events=events,
                             damage_model=dm, month=a.month, seed=a.seed, trace_every=a.log_every,
                             trace_days=sim.parse_days(a.log_days), trace_lines=trace)
    
    outdir = config.OUTPUT / (a.month + ("_toy" if a.toy else ""))
    outdir.mkdir(parents=True, exist_ok=True)
    
    # 1. Zapisuje tylko surowy plik CSV z wynikami symulacji
    log.to_csv(outdir / "truck_log.csv", index=False)
    
    # 2. Tworzymy tabele podsumowujące (q - przejścia, h - huby)
    q, h = report.summarize(log)
    q.to_csv(outdir / "summary_crossings.csv")
    h.to_csv(outdir / "summary_hubs.csv")
    
    if trace:
        trace.sort(key=lambda s: (s[1:13]))  # chronologicznie (dz.DD GG:MM)
        (outdir / "sim_log.txt").write_text("\n".join(trace), encoding="utf-8")

    # 3. Drukujemy na ekran tylko to, co czyste i merytoryczne:
    print("\nPrzejścia:\n", q.to_string())
    print("\nHuby:\n", h.to_string())
    
    replans_count = (log['replans'] > 0).sum()
    stuck_count = (log['stuck_min'] > 0).sum()
    stuck_sum = log['stuck_min'].sum()
    print(f"\nZdarzenia: {len(events)}; ciężarówek ze zmianą trasy: {replans_count}; "
          f"czekało bez drogi: {stuck_count} (łącznie {stuck_sum:.0f} min)")
    
    print(f"\n Symulacja zakończona. Wyniki zapisano w: {outdir}/truck_log.csv")

if __name__ == "__main__":
    main()
