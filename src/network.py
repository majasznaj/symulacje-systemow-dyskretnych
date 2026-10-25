"""Krok 2: graf dróg Strefy Gazy (pobranie raz, zapis do pliku) i trasy (D* Lite)."""
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
                G = ox.truncate.largest_component(G, strongly=config.GRAPH_STRONGLY_CONNECTED)
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


def compute_routes(G, crossing_nodes, hub_nodes, router):
    """Trasy bazowe (stan dróg w chwili wywołania) dla każdej pary (przejście, hub) z pól D* Lite.

    Zwraca {(przejście, hub): {path, edge_min, edge_km, km, minutes, shortest_km, detour_km}}.
    shortest_km to najkrótsza trasa bez zniszczeń i blokad (też D* Lite, z kosztem = długość).
    """
    import router as router_mod
    length_router = router_mod.FieldRouter(G, hub_nodes, next(iter(crossing_nodes.values())),
                                           cost_fn=router_mod.length_cost)
    routes = {}
    for c, u in crossing_nodes.items():
        for h in hub_nodes:
            path = router.plan(h, u)
            edge_min, edge_km = [], []
            a = u
            for b in path:
                dt, dkm = router.edge(a, b)
                edge_min.append(dt); edge_km.append(dkm)
                a = b
            short = length_router.plan(h, u)
            a, short_km = u, 0.0
            for b in short:
                short_km += length_router.edge(a, b)[1]
                a = b
            routes[(c, h)] = {"path": [u] + path, "edge_min": edge_min, "edge_km": edge_km,
                              "km": sum(edge_km), "minutes": sum(edge_min),
                              "shortest_km": short_km, "detour_km": sum(edge_km) - short_km}
    return routes
