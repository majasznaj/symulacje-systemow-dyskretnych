"""Uruchamianie M1.

Kolejność pierwszego razu (np. w Colabie):
  python run.py --prepare-data      # krok 3 i 4: Excel -> data/processed
  python run.py --build-graph       # krok 2: graf z Overpass -> data/processed/gaza_drive.graphml
  python run.py --describe-unosat   # krok 5: diagnostyka kolumn SensorDate
  python run.py                     # kroki 5-7: cała symulacja
Test kodu bez sieci i bez UNOSAT: python run.py --toy
"""
import argparse

import config
import damage
import data
import network
import report
import sim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=config.MONTH)
    ap.add_argument("--prepare-data", action="store_true", help="Excel -> data/processed")
    ap.add_argument("--build-graph", action="store_true", help="pobierz graf z Overpass")
    ap.add_argument("--describe-unosat", action="store_true", help="pokaż kolumny i daty UNOSAT")
    ap.add_argument("--toy", action="store_true", help="sztuczny graf i zniszczenia (test kodu)")
    ap.add_argument("--no-damage", action="store_true")
    ap.add_argument("--damage-as-of", default=config.DAMAGE_AS_OF)
    ap.add_argument("--seed", type=int, default=config.SEED)
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

    # --- dane (kroki 3-4) ---
    trucks, shares = data.prepare(a.month)

    # --- graf (krok 2) ---
    if a.toy:
        import toy
        graph_file = config.DATA_PROC / "toy_graph.graphml"
        toy.make_toy_graph(graph_file)
        G = network.load_graph(graph_file)
    else:
        G = network.load_graph()
    crossing_nodes = network.snap_points(G, config.CROSSINGS)
    hub_nodes = network.snap_points(G, config.HUBS)

    # --- zniszczenia (krok 5) ---
    damage.set_base_weights(G)
    if config.USE_DAMAGE and not a.no_damage:
        gdf = toy.make_toy_damage() if a.toy else damage.load_unosat()
        damage.apply_damage(G, damage.filter_as_of(gdf, a.damage_as_of))
    routes = network.compute_routes(G, crossing_nodes, hub_nodes)

    # --- symulacja (krok 6) i raport (krok 7) ---
    log = sim.run_simulation(trucks, routes, shares, month=a.month, seed=a.seed)
    outdir = config.OUTPUT / (a.month + ("_toy" if a.toy else ""))
    outdir.mkdir(parents=True, exist_ok=True)
    log.to_csv(outdir / "truck_log.csv", index=False)
    q, h = report.summarize(log)
    q.to_csv(outdir / "summary_crossings.csv"); h.to_csv(outdir / "summary_hubs.csv")
    report.make_plots(trucks, log, outdir)

    print("\nPrzejścia:\n", q.to_string())
    print("\nHuby:\n", h.to_string())
    print("\nSprawdzenia:")
    for desc, ok in report.checks(trucks, log):
        print(f"  [{'OK' if ok else 'BŁĄD'}] {desc}")
    print(f"\nWyniki w {outdir}")


if __name__ == "__main__":
    main()
