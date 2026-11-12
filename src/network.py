"""Krok 2: graf dróg Strefy Gazy (pobranie raz, zapis do pliku) i trasy (D* Lite)."""
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point

import config


def road_filter():
    """Filtr Overpass: jak 'drive' z osmnx, ale z drogami service i track. None = zwykłe 'drive'."""
    if not config.USE_EXTRA_ROAD_TYPES:
        return None
    return ('["highway"]["area"!~"yes"]["access"!~"private"]'
            f'["highway"!~"{config.ROAD_EXCLUDED}"]'
            '["motor_vehicle"!~"no"]["motorcar"!~"no"]'
            '["service"!~"emergency_access|parking|parking_aisle|private"]')


def gaza_polygon():
    """Granica Strefy (Nominatim) powiększona o config.GAZA_CLIP_BUFFER_M, bo przejścia leżą na samej granicy.

    Bufor jest mały (500 m), żeby do grafu nie weszły drogi izraelskie ani egipskie, którymi ciężarówki
    miałyby skróty poza Strefą. Zwraca None, gdy nie ma sieci albo Nominatim nie odpowiada.
    """
    try:
        gdf = ox.geocode_to_gdf("Gaza Strip")
        metric = gdf.estimate_utm_crs()
        poly = gdf.to_crs(metric).buffer(config.GAZA_CLIP_BUFFER_M).to_crs("EPSG:4326").iloc[0]
        return poly
    except Exception as e:  # noqa: BLE001
        print(f"  granica Strefy niedostępna ({type(e).__name__}): graf nie zostanie przycięty do granicy")
        return None


def clip_to_gaza(G, poly):
    """Zostawia węzły wewnątrz poly i największą spójną składową. Bez poly zwraca G bez zmian."""
    if poly is None:
        return G
    nodes = ox.graph_to_gdfs(G, edges=False)
    H = G.subgraph(nodes.index[nodes.within(poly)]).copy()
    return ox.truncate.largest_component(H, strongly=config.GRAPH_STRONGLY_CONNECTED)


def build_graph(path=None, network_type="drive"):
    """Pobiera sieć dróg z Overpass i zapisuje do pliku. Uruchamiasz RAZ (python run.py --build-graph).

    Graf jest przycięty do granicy Strefy + 500 m. Bez przycinania (prostokąt GAZA_BBOX obejmuje też Izrael)
    graf miał ponad 30 tys. węzłów, a trasy mogły iść drogami poza Strefą.
    """
    path = path or config.GRAPH_FILE
    ox.settings.requests_timeout = 300
    last_err = None
    poly = gaza_polygon()
    ways = (["polygon"] if poly is not None else []) + ["bbox"]
    for url in config.OVERPASS_URLS:
        if hasattr(ox.settings, "overpass_url"):
            ox.settings.overpass_url = url
        else:  # starsze wersje osmnx
            ox.settings.overpass_endpoint = url
        for how in ways:
            try:
                print(f"Pobieram graf: {url} ({how})...")
                if how == "polygon":
                    G = ox.graph_from_polygon(poly, network_type=network_type, custom_filter=road_filter())
                else:
                    G = ox.graph_from_bbox(bbox=config.GAZA_BBOX, network_type=network_type, custom_filter=road_filter())
                G = clip_to_gaza(G, poly)
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

    Zwraca {(przejście, hub): {path, edge_min, edge_km, km, minutes}}.
    """
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
            routes[(c, h)] = {"path": [u] + path, "edge_min": edge_min, "edge_km": edge_km,
                              "km": sum(edge_km), "minutes": sum(edge_min)}
    return routes
