"""Diagnostyka grafu: dlaczego wokół Rafah prawie nie ma dróg.

Zapisany graf (data/processed/gaza_drive.graphml) jest już PO wycięciu składowych przez build_graph, więc sam
nie powie, co zostało wycięte. Porównujemy go z surowym grafem południa Strefy z OSM (jedno małe zapytanie
do Overpass, z ponawianiem przy błędzie 502). Uruchomienie:  python src/run.py --graph-check [--offline]
"""
import time

import networkx as nx
import numpy as np
import osmnx as ox

import config

RAFAH_CITY = (31.2833, 34.2500)   # środek miasta, współrzędne przybliżone (Wikipedia), tylko do diagnostyki
SOUTH_BBOX = (34.20, 31.20, 34.40, 31.36)   # (zachód, południe, wschód, północ)


def _arrays(G, nodes=None):
    ids = list(G.nodes if nodes is None else nodes)
    return np.array([G.nodes[n]["y"] for n in ids]), np.array([G.nodes[n]["x"] for n in ids])


def near(G, lat, lon, radius_m, nodes=None):
    ys, xs = _arrays(G, nodes)
    if len(ys) == 0:
        return 0
    return int((ox.distance.great_circle(lat, lon, ys, xs) < radius_m).sum())


def conclude(n_raw, n_strong, n_saved):
    """Wniosek z trzech liczb: węzły wokół Rafah w surowym grafie, w jego silnie spójnej części i w zapisanym grafie."""
    if n_raw <= 3 * max(n_saved, 1):
        return ("OSM ma wokół Rafah rzadką sieć już w surowych danych (typ 'drive'). Zmień network_type na 'all' "
                "albo przesuń hub tam, gdzie sieć jest gęsta.")
    if n_strong <= n_raw / 3:
        return ("Sieć wokół Rafah jest w OSM, ale wycina ją warunek silnej spójności (jednokierunkowa luka). "
                "Ustaw GRAPH_STRONGLY_CONNECTED = False w config.py i uruchom --build-graph.")
    return ("Sieć wokół Rafah jest w OSM i jest silnie spójna, a w zapisanym grafie jej brak: obrys 'Gaza Strip' "
            "z place ucina południe. Pobierz graf po bbox (graph_from_bbox) zamiast po place.")


def report(G, label, radius_m=2000, top=6, saved=None):
    """Wypisuje składowe spójne i gęstość sieci wokół punktów. saved = zapisany graf, do porównania (opcjonalnie)."""
    weak = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    strong = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    big_w, big_s = weak[0], strong[0]
    print(f"\n=== {label}: {len(G.nodes)} węzłów, {len(G.edges)} krawędzi ===")
    print(f"składowe słabo spójne: {len(weak)}, największa {len(big_w)} węzłów; "
          f"silnie spójne: {len(strong)}, największa {len(big_s)} węzłów")
    print(f"wycięte przez silną spójność: {len(G.nodes) - len(big_s)} węzłów (przez słabą: {len(G.nodes) - len(big_w)})")
    print("największe składowe słabo spójne (rozmiar, środek lat/lon):")
    for comp in weak[:top]:
        ys, xs = _arrays(G, comp)
        print(f"   {len(comp):6d} węzłów, środek ({ys.mean():.3f}, {xs.mean():.3f})")
    points = {**config.CROSSINGS, **config.HUBS, "Rafah miasto (przybl.)": RAFAH_CITY}
    head = "surowy | najw. słabo spójna | najw. silnie spójna" + (" | zapisany graf" if saved is not None else "")
    print(f"węzły w promieniu {radius_m / 1000:.0f} km od punktu: {head}")
    out = {}
    for name, (lat, lon) in points.items():
        row = (near(G, lat, lon, radius_m), near(G, lat, lon, radius_m, big_w), near(G, lat, lon, radius_m, big_s))
        if saved is not None:
            row += (near(saved, lat, lon, radius_m),)
        out[name] = row
        print(f"   {name:24s} " + " | ".join(f"{v:6d}" for v in row))
    return {"weak": len(weak), "strong": len(strong), "big_weak": len(big_w), "big_strong": len(big_s), "near": out}


def fetch_south(attempts=4, wait_s=30):
    """Surowy graf południa (bbox), z ponawianiem: Overpass często odpowiada 502, gdy jest przeciążony."""
    ox.settings.requests_timeout = 180
    last = None
    for attempt in range(1, attempts + 1):
        for url in config.OVERPASS_URLS:
            ox.settings.overpass_url = url
            try:
                print(f"Próba {attempt}/{attempts}, serwer {url}: surowy graf południa (lat 31.20-31.36, lon 34.20-34.40)...")
                return ox.graph_from_bbox(bbox=SOUTH_BBOX, network_type="drive", retain_all=True)
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"  nie wyszło: {type(e).__name__}: {str(e).splitlines()[0][:110]}")
        if attempt < attempts:
            print(f"Wszystkie serwery zajęte, czekam {wait_s} s...")
            time.sleep(wait_s)
    raise RuntimeError(f"Overpass nie odpowiada po {attempts} próbach: {last}. Spróbuj za kilkanaście minut.")


def run(offline=False):
    saved = ox.load_graphml(config.GRAPH_FILE) if config.GRAPH_FILE.exists() else None
    if saved is None:
        print(f"Uwaga: brak {config.GRAPH_FILE}, porównanie z zapisanym grafem pominięte.")
    if offline:
        if saved is None:
            raise SystemExit("Tryb --offline potrzebuje zapisanego grafu (python src/run.py --build-graph).")
        report(saved, "ZAPISANY GRAF (bez Overpass)")
        print("\nTryb offline pokazuje tylko, jak gęsta jest sieć w zapisanym grafie. Nie rozstrzyga, czy dróg brakuje "
              "w OSM, czy wycięła je budowa grafu: do tego potrzebny jest surowy graf (uruchom bez --offline, gdy Overpass odpowiada).")
        return
    G = fetch_south()
    r = report(G, "SUROWY GRAF POŁUDNIA (bbox)", saved=saved)
    row = r["near"]["Rafah miasto (przybl.)"]
    n_raw, n_strong = row[0], row[2]
    n_saved = row[3] if saved is not None else 0
    print("\n=== WNIOSEK ===")
    print(f"Wokół środka Rafah (2 km): surowy graf {n_raw} węzłów, z tego silnie spójnych {n_strong}, "
          f"w zapisanym grafie {n_saved}.")
    print("->", conclude(n_raw, n_strong, n_saved))
