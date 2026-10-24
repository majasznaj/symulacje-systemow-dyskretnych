"""Krok 2: graf dróg Strefy Gazy (pobranie raz, zapis do pliku) i trasy A*."""
import math
import networkx as nx
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point

import config


def build_graph(path=None, network_type="drive"):
    """Pobiera sieć dróg z Overpass i zapisuje do pliku. Uruchamiasz RAZ (python run.py --build-graph)."""
    path = path or config.GRAPH_FILE
    ox.settings.requests_timeout = 300
    last_err = None
    for url in config.OVERPASS_URLS:
        if hasattr(ox.settings, "overpass_url"):
            ox.settings.overpass_url = url
        else:  # starsze wersje osmnx
            ox.settings.overpass_endpoint = url
        for how in ("place", "bbox"):
            try:
                print(f"Pobieram graf: {url} ({how})...")
                if how == "place":
                    G = ox.graph_from_place("Gaza Strip", network_type=network_type)
                else:
                    G = ox.graph_from_bbox(bbox=config.GAZA_BBOX, network_type=network_type)
                G = ox.truncate.largest_component(G, strongly=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                ox.save_graphml(G, path)
                print(f"Zapisano {path} ({len(G.nodes)} węzłów, {len(G.edges)} krawędzi)")
                return G
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"  nie wyszło: {type(e).__name__}: {str(e)[:150]}")
    raise RuntimeError(
        "Nie udało się pobrać grafu z żadnego serwera Overpass. Pobierz go na innym komputerze "
        f"albo w innej porze i wrzuć plik jako {path}. Ostatni błąd: {last_err}"
    )


def load_graph(path=None):
    """Wczytuje graf z pliku i rzutuje na układ metryczny (UTM)."""
    path = path or config.GRAPH_FILE
    if not path.exists():
        raise FileNotFoundError(f"Brak {path}. Uruchom najpierw: python run.py --build-graph")
    return ox.project_graph(ox.load_graphml(path))


def snap_points(G, points, warn_km=2.0):
    """Przypisuje punkty (lat, lon) do najbliższych węzłów grafu. Zwraca {nazwa: węzeł}."""
    nodes = ox.graph_to_gdfs(G, edges=False)
    out = {}
    for name, (lat, lon) in points.items():
        p = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(nodes.crs).iloc[0]
        d = nodes.geometry.distance(p)
        out[name] = d.idxmin()
        if d.min() > warn_km * 1000:
            print(f"UWAGA: {name} jest {d.min() / 1000:.1f} km od najbliższej drogi")
    return out


def _best_edge(G, u, v, weight):
    """Z równoległych krawędzi u->v bierze tę o najmniejszym koszcie."""
    return min(G[u][v].values(), key=lambda d: d.get(weight, d["length"]))


def compute_routes(G, crossing_nodes, hub_nodes):
    """Trasa A* dla każdej pary (przejście, hub). Zniszczenia są statyczne, więc liczymy raz.

    Zwraca {(przejście, hub): {km, minutes, shortest_km, detour_km}}.
    """
    def heuristic(a, b):  # odległość w linii prostej (metry) nie przekracza kosztu
        return math.hypot(G.nodes[a]["x"] - G.nodes[b]["x"], G.nodes[a]["y"] - G.nodes[b]["y"])

    routes = {}
    for c, u in crossing_nodes.items():
        for h, v in hub_nodes.items():
            path = nx.astar_path(G, u, v, heuristic=heuristic, weight="cost")
            shortest = nx.astar_path(G, u, v, heuristic=heuristic, weight="length")
            km = minutes = 0.0
            for a, b in zip(path[:-1], path[1:]):
                e = _best_edge(G, a, b, "cost")
                km += e["length"] / 1000
                minutes += e["time_min"]
            short_km = sum(_best_edge(G, a, b, "length")["length"] for a, b in zip(shortest[:-1], shortest[1:])) / 1000
            routes[(c, h)] = {"km": km, "minutes": minutes, "shortest_km": short_km,
                              "detour_km": km - short_km, "path": path}
    return routes
