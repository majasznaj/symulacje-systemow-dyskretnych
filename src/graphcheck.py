"""Diagnostyka grafu: co wycina build_graph i czy sieć wokół Rafah w ogóle jest w danych OSM.

Wymaga Overpass (Colab):  python src/run.py --graph-check
Pobiera surowy graf (bez wycinania składowych) i pokazuje składowe spójne oraz liczbę węzłów
w pobliżu przejść i hubów: w surowym grafie, w największej słabo spójnej i w największej silnie spójnej.
"""
import networkx as nx
import numpy as np
import osmnx as ox

import config

RAFAH_CITY = (31.2833, 34.2500)   # środek miasta, współrzędne przybliżone (Wikipedia), tylko do diagnostyki


def _arrays(G, nodes=None):
    ids = list(G.nodes if nodes is None else nodes)
    return np.array([G.nodes[n]["y"] for n in ids]), np.array([G.nodes[n]["x"] for n in ids])


def near(G, lat, lon, radius_m, nodes=None):
    ys, xs = _arrays(G, nodes)
    if len(ys) == 0:
        return 0
    return int((ox.distance.great_circle(lat, lon, ys, xs) < radius_m).sum())


def report(G, label, radius_m=2000, top=6):
    """Wypisuje składowe spójne i gęstość sieci wokół punktów. Zwraca słownik z liczbami (do testów)."""
    weak = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    strong = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    big_w, big_s = weak[0], strong[0]
    print(f"\n=== {label}: {len(G.nodes)} węzłów, {len(G.edges)} krawędzi ===")
    print(f"składowe słabo spójne: {len(weak)}, największa {len(big_w)} węzłów; "
          f"silnie spójne: {len(strong)}, największa {len(big_s)} węzłów")
    print(f"wycięte przez silną spójność: {len(G.nodes) - len(big_s)} węzłów "
          f"(przez słabą: {len(G.nodes) - len(big_w)})")
    print("największe składowe słabo spójne (rozmiar, środek lat/lon):")
    for comp in weak[:top]:
        ys, xs = _arrays(G, comp)
        print(f"   {len(comp):6d} węzłów, środek ({ys.mean():.3f}, {xs.mean():.3f})")
    points = {**config.CROSSINGS, **config.HUBS, "Rafah miasto (przybl.)": RAFAH_CITY}
    print(f"węzły w promieniu {radius_m / 1000:.0f} km od punktu: surowy graf | najw. słabo spójna | najw. silnie spójna")
    out = {}
    for name, (lat, lon) in points.items():
        a, b, c = near(G, lat, lon, radius_m), near(G, lat, lon, radius_m, big_w), near(G, lat, lon, radius_m, big_s)
        out[name] = (a, b, c)
        print(f"   {name:24s} {a:6d} | {b:6d} | {c:6d}")
    return {"weak": len(weak), "strong": len(strong), "big_weak": len(big_w), "big_strong": len(big_s), "near": out}


def run():
    ox.settings.requests_timeout = 300
    last = None
    for url in config.OVERPASS_URLS:
        ox.settings.overpass_url = url
        try:
            print(f"Serwer {url}: surowy graf całej Strefy (place, retain_all=True)...")
            G_place = ox.graph_from_place("Gaza Strip", network_type="drive", retain_all=True)
            print("Surowy graf południa (bbox lat 31.20-31.36, lon 34.20-34.40)...")
            G_south = ox.graph_from_bbox(bbox=(34.20, 31.20, 34.40, 31.36), network_type="drive", retain_all=True)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  nie wyszło: {type(e).__name__}: {str(e)[:150]}")
    else:
        raise RuntimeError(f"Overpass nie odpowiada: {last}")
    r1 = report(G_place, "CAŁA STREFA (place)")
    r2 = report(G_south, "POŁUDNIE (bbox)")
    n_place, _, s_place = r1["near"]["Rafah miasto (przybl.)"]
    n_south = r2["near"]["Rafah miasto (przybl.)"][0]
    print("\n=== WNIOSEK ===")
    print(f"Wokół środka Rafah (2 km): place {n_place} węzłów, bbox {n_south}, po silnej spójności {s_place}.")
    if n_south > 3 * max(n_place, 1):
        print("-> obrys 'Gaza Strip' z place ucina południe. Użyj pobierania po bbox.")
    elif n_place > 3 * max(s_place, 1):
        print("-> sieć wokół Rafah jest w OSM, ale wycina ją warunek silnej spójności (jednokierunkowe luki). "
              "Ustaw GRAPH_STRONGLY_CONNECTED = False w config.py i uruchom --build-graph.")
    else:
        print("-> sieć wokół Rafah jest rzadka już w surowych danych OSM (typ 'drive'). Trzeba zmienić "
              "network_type na 'all' albo przesunąć hub w gęściej zmapowane miejsce.")
