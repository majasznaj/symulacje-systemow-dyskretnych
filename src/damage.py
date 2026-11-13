"""Krok 5: zniszczenia UNOSAT -> koszt i czas przejazdu krawędzi grafu."""
import glob
import zipfile
from collections import defaultdict

import geopandas as gpd
import numpy as np
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
    if not glob.glob(str(target / "**" / "*.gdb"), recursive=True):   # rozpakowujemy tylko za pierwszym razem
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(target)
    gdb = glob.glob(str(target / "**" / "*.gdb"), recursive=True)[0]
    layers = pyogrio.list_layers(gdb)
    layer = [name for name, geom in layers if "Point" in str(geom)][0]
    gdf = gpd.read_file(gdb, layer=layer)
    print(f"UNOSAT: warstwa {layer}, {len(gdf)} punktów")
    # legenda z samego pliku .gdb (domena damage_type): 1 zniszczony, 2 poważnie, 3 średnio, 4 możliwe uszkodzenie,
    # 6 BRAK widocznych uszkodzeń, 11 możliwe uszkodzenie od sąsiedniego uderzenia/gruzu. Klasa 6 nie jest zniszczeniem.
    last = [c for c in gdf.columns if c.startswith("Main_Damage_Site_Class")][-1]
    ok = gdf[last] != 6
    if (~ok).any():
        print(f"UNOSAT: pominięto {int((~ok).sum())} punktów z klasą 6 ('No Visible Damage')")
        gdf = gdf[ok]
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


def first_info(gdf):
    """Data pierwszego zdjęcia, na którym punkt jest uszkodzony, i klasa uszkodzenia z tego zdjęcia.

    Kolumna SensorDate_k to data k-tego przelotu, a Main_Damage_Site_Class_k to klasa z tego przelotu (pusta albo 6 = brak
    uszkodzenia). Bierzemy najwcześniejszą datę, przy której klasa jest niepusta i różna od 6.
    """
    best, best_cls = None, None
    for c in [c for c in gdf.columns if c.startswith("SensorDate")]:
        cls = gdf[c.replace("SensorDate", "Main_Damage_Site_Class")]
        d = pd.to_datetime(gdf[c], errors="coerce", utc=True).where(cls.notna() & (cls != 6))
        if best is None:
            best, best_cls = d, cls.where(d.notna())
            continue
        better = d.notna() & (best.isna() | (d < best))
        best, best_cls = best.where(~better, d), best_cls.where(~better, cls)
    return best, best_cls


def first_dates(gdf):
    return first_info(gdf)[0] if "first" not in gdf.columns else gdf["first"]


def prepare_points(gdf):
    """Dokłada kolumny: first (data zdjęcia), w (waga klasy) i expires (koniec odgruzowania).

    Czas odgruzowania każdego punktu jest losowany raz z U(DEBRIS_CLEAR_DAYS) własnym generatorem (stałe ziarno
    DEBRIS_SEED), więc jest ten sam w każdym miesiącu i w każdym przebiegu. Punkt znika z dróg w dniu first + czas.
    """
    first, cls = first_info(gdf)
    out = gdf.copy()
    out["first"] = first
    out["w"] = cls.map(config.DAMAGE_CLASS_WEIGHT).fillna(config.DAMAGE_DEFAULT_WEIGHT).astype(float)
    if config.DEBRIS_CLEAR_DAYS:
        lo, hi = config.DEBRIS_CLEAR_DAYS
        days = np.random.default_rng(config.DEBRIS_SEED).uniform(lo, hi, len(out))
        out["expires"] = first + pd.to_timedelta(days, unit="D")
    else:
        out["expires"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    return out


def filter_as_of(gdf, as_of):
    """Punkty widoczne na as_of: już sfotografowane i jeszcze nieodgruszczone."""
    if as_of is None:
        return gdf
    as_of = pd.Timestamp(as_of, tz="UTC")
    kept = (gdf["first"] <= as_of) & (gdf["expires"].isna() | (gdf["expires"] > as_of))
    out = gdf[kept]
    print(f"Zniszczenia na {as_of.date()}: {len(out)} z {len(gdf)} punktów (waga {out['w'].sum():.0f})")
    return out


def speed_factor(d):
    """Mnożnik prędkości swobodnej zależny od typu drogi (najwolniejszy typ, gdy krawędź ma kilka tagów)."""
    hw = d.get("highway")
    hw = hw if isinstance(hw, list) else [hw]
    return min((config.ROAD_SPEED_FACTOR.get(h, 1.0) for h in hw), default=1.0)


def set_base_weights(G):
    """Bez zniszczeń: czas przejazdu krawędzi = długość / prędkość [min]. Router używa właśnie tego czasu."""
    v = config.TRUCK_SPEED_KMH * 1000 / 60  # m/min
    for _, _, _, d in G.edges(keys=True, data=True):
        d["damage"] = 0
        d["speed_factor"] = speed_factor(d)
        d["time_min"] = d["length"] / (v * d["speed_factor"])


class DamageModel:
    """Zniszczenia UNOSAT na krawędziach grafu, z możliwością dokładania nowych punktów w trakcie symulacji.

    Dla krawędzi bierzemy maksimum zliczeń z oczek siatki, przez które przechodzi (jak w waszym notebooku).
    Dla każdej krawędzi pamiętamy jej oczka, a dla każdego oczka jego krawędzie, więc nowa fala punktów
    przelicza tylko krawędzie, których to dotyczy.
    """

    def __init__(self, G, gdf):
        self.G = G
        self.cell = config.DAMAGE_CELL_M
        self.counts = {}
        self.edge_cells, self.cell_edges = {}, defaultdict(list)
        edges = ox.graph_to_gdfs(G, nodes=False)
        for (u, v, k), geom, length in zip(edges.index, edges.geometry, edges["length"]):
            n = max(2, int(length // (self.cell / 2)) + 2)
            cells = set()
            for i in range(n):
                p = geom.interpolate(i / (n - 1), normalized=True)
                cells.add((int(p.x // self.cell), int(p.y // self.cell)))
            self.edge_cells[(u, v, k)] = cells
            for c in cells:
                self.cell_edges[c].append((u, v, k))
        self.add_points(gdf)
        hit = sum(1 for (u, v, k) in self.edge_cells if G[u][v][k]["damage"] > 0)
        print(f"Zniszczenia nałożone: {hit} z {len(self.edge_cells)} krawędzi przechodzi przez oczka ze zniszczeniami")

    def _refresh(self, u, v, k):
        dmg = max((self.counts.get(c, 0) for c in self.edge_cells[(u, v, k)]), default=0)
        d = self.G[u][v][k]
        length = d["length"]
        v_free = config.TRUCK_SPEED_KMH * 1000 / 60 * speed_factor(d)
        v_min = min(config.MIN_SPEED_KMH * 1000 / 60, v_free)
        # jeden wzór: ciężarówka jedzie wolniej, a router dostaje ten sam czas
        d["damage"] = round(float(dmg), 2)
        d["time_min"] = length / max(v_min, v_free / (1 + config.SLOWDOWN_PER_DAMAGE * dmg))

    def _cell_counts(self, gdf):
        """Suma wag punktów w każdym oczku: {oczko: waga}."""
        pts = gdf.to_crs(self.G.graph["crs"])
        kx = (pts.geometry.x // self.cell).astype(int).to_numpy()
        ky = (pts.geometry.y // self.cell).astype(int).to_numpy()
        return pd.Series(gdf["w"].to_numpy()).groupby([kx, ky]).sum().to_dict()

    def _touch(self, cells):
        touched = set()
        for cell in cells:
            touched.update(self.cell_edges.get(cell, ()))
        for (u, v, k) in touched:
            self._refresh(u, v, k)
        return {(u, v) for (u, v, k) in touched}

    def add_points(self, gdf):
        """Dokłada punkty zniszczeń. Zwraca zbiór par (u, v), których koszt się zmienił."""
        if len(gdf) == 0:
            return set()
        new = self._cell_counts(gdf)
        for cell, n in new.items():
            self.counts[cell] = self.counts.get(cell, 0.0) + n
        return self._touch(new)

    def remove_points(self, gdf):
        """Zdejmuje punkty (odgruzowanie). Zwraca krawędzie, których koszt się zmienił."""
        if len(gdf) == 0:
            return set()
        gone = self._cell_counts(gdf)
        for cell, n in gone.items():
            left = self.counts.get(cell, 0) - n
            if left > 1e-6:
                self.counts[cell] = left
            else:
                self.counts.pop(cell, None)
        return self._touch(gone)
