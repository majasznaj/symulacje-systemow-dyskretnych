"""Sztuczny graf i zniszczenia do sprawdzania kodu bez Overpass i bez UNOSAT (python run.py --toy)."""
import geopandas as gpd
import numpy as np
import osmnx as ox
from shapely.geometry import LineString, Point

import config


def make_toy_graph(path, seed=0):
    rng = np.random.default_rng(seed)
    lats = np.arange(31.20, 31.601, 0.01)
    lons = np.arange(34.20, 34.571, 0.01)
    ids = {(i, j): i * len(lons) + j for i in range(len(lats)) for j in range(len(lons))}
    nodes = gpd.GeoDataFrame(
        {"y": [lats[i] for i, j in ids], "x": [lons[j] for i, j in ids]},
        index=list(ids.values()), geometry=[Point(lons[j], lats[i]) for i, j in ids], crs="EPSG:4326")
    rows = []
    for (i, j), u in ids.items():
        for di, dj in ((1, 0), (0, 1)):
            if (i + di, j + dj) in ids and rng.random() > 0.12:  # część dróg znika
                v = ids[(i + di, j + dj)]
                length = float(ox.distance.great_circle(lats[i], lons[j], lats[i + di], lons[j + dj]))
                geom = LineString([(lons[j], lats[i]), (lons[j + dj], lats[i + di])])
                rows.append((u, v, 0, length, geom, "residential", False))
                rows.append((v, u, 0, length, geom.reverse(), "residential", False))
    edges = gpd.GeoDataFrame(rows, columns=["u", "v", "key", "length", "geometry", "highway", "oneway"],
                             crs="EPSG:4326").set_index(["u", "v", "key"])
    G = ox.graph_from_gdfs(nodes, edges)
    G = ox.truncate.largest_component(G, strongly=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, path)
    return G


def make_toy_damage(seed=0, n=40000):
    rng = np.random.default_rng(seed)
    centers = [(31.50, 34.46), (31.345, 34.30), (31.29, 34.25), (31.42, 34.35)]
    pts = []
    for lat, lon in centers:
        k = n // len(centers)
        pts += list(zip(rng.normal(lon, 0.025, k), rng.normal(lat, 0.02, k)))
    dates = np.datetime64("2023-10-15") + rng.integers(0, 537, len(pts)).astype("timedelta64[D]")
    return gpd.GeoDataFrame({"SensorDate": dates}, geometry=[Point(x, y) for x, y in pts], crs="EPSG:4326")
