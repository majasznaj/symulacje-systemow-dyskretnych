"""Krok 5: zniszczenia UNOSAT -> koszt i czas przejazdu krawędzi grafu."""
import glob
import math
import zipfile
from collections import Counter

import geopandas as gpd
import osmnx as ox
import pandas as pd

import config


def load_unosat(zip_path=None):
    """Rozpakowuje archiwum UNOSAT i wczytuje warstwę punktową ze zniszczeniami."""
    import pyogrio
    zip_path = zip_path or config.UNOSAT_ZIP
    if not zip_path.exists():
        raise FileNotFoundError(f"Brak {zip_path}. Wrzuć tam plik UNOSAT (zip z .gdb).")
    target = config.DATA_PROC / "unosat_extracted"
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(target)
    gdb = glob.glob(str(target / "**" / "*.gdb"), recursive=True)[0]
    layers = pyogrio.list_layers(gdb)
    layer = [name for name, geom in layers if "Point" in str(geom)][0]
    gdf = gpd.read_file(gdb, layer=layer)
    print(f"UNOSAT: warstwa {layer}, {len(gdf)} punktów")
    return gdf


def describe_unosat(gdf):
    """Diagnostyka: czy kolumny SensorDate_N dają prawdziwą oś czasu zniszczeń?"""
    print("Kolumny:", list(gdf.columns))
    for col in [c for c in gdf.columns if c.startswith("SensorDate")]:
        d = pd.to_datetime(gdf[col], errors="coerce")
        print(f"\n{col}: {d.notna().sum()} wartości, {d.nunique()} unikalnych dat, "
              f"{d.min()} .. {d.max()}")
        print(d.dt.to_period("M").value_counts().sort_index().to_string())
    for col in [c for c in gdf.columns if c.startswith("Main_Damage_Site_Class")]:
        print(f"\n{col}:\n{gdf[col].value_counts(dropna=False).to_string()}")

def first_dates(gdf):
    """Data pierwszego zdjęcia każdego punktu = najwcześniejsza z kolumn SensorDate, SensorDate_2, ..."""
    cols = [c for c in gdf.columns if c.startswith("SensorDate")]
    d = pd.concat([pd.to_datetime(gdf[c], errors="coerce", utc=True) for c in cols], axis=1)
    return d.min(axis=1)

def filter_as_of(gdf, as_of):
    """Zostawia punkty, które były już zauważone na zdjęciu nie późniejszym niż as_of."""
    if as_of is None:
        return gdf
    kept = gdf[first_dates(gdf) <= pd.Timestamp(as_of, tz="UTC")]
    print(f"Zniszczenia na {as_of}: {len(kept)} z {len(gdf)} punktów")
    return kept


def set_base_weights(G):
    """Bez zniszczeń: koszt = długość, czas = długość / prędkość."""
    v = config.TRUCK_SPEED_KMH * 1000 / 60  # m/min
    for _, _, _, d in G.edges(keys=True, data=True):
        d["damage"] = 0
        d["cost"] = d["length"]
        d["time_min"] = d["length"] / v


def apply_damage(G, damage_gdf):
    """Zlicza punkty w oczkach siatki i wpisuje do krawędzi damage, cost i time_min.

    Dla krawędzi bierzemy maksimum zliczeń z oczek, przez które przechodzi (jak w waszym notebooku).
    """
    cell = config.DAMAGE_CELL_M
    pts = damage_gdf.to_crs(G.graph["crs"])
    counts = Counter(zip((pts.geometry.x // cell).astype(int), (pts.geometry.y // cell).astype(int)))
    edges = ox.graph_to_gdfs(G, nodes=False)
    v_free = config.TRUCK_SPEED_KMH * 1000 / 60
    v_min = config.MIN_SPEED_KMH * 1000 / 60
    hit = 0
    for (u, v, k), geom, length in zip(edges.index, edges.geometry, edges["length"]):
        n = max(2, int(length // (cell / 2)) + 2)
        dmg = 0
        for i in range(n):
            p = geom.interpolate(i / (n - 1), normalized=True)
            dmg = max(dmg, counts.get((int(p.x // cell), int(p.y // cell)), 0))
        mult = min(config.MAX_COST_MULTIPLIER, 1 + config.DAMAGE_PENALTY * dmg ** config.DAMAGE_EXPONENT)
        speed = max(v_min, v_free / (1 + config.SLOWDOWN_PER_DAMAGE * dmg))
        d = G[u][v][k]
        d["damage"] = int(dmg)
        d["cost"] = length * mult
        d["time_min"] = length / speed
        hit += dmg > 0
    print(f"Zniszczenia nałożone: {hit} z {len(edges)} krawędzi przechodzi przez oczka ze zniszczeniami")
