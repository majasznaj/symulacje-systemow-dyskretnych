"""Diagnostyka grafu dróg, przypięcia punktów i zniszczeń: python src/run.py --diagnose"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import osmnx as ox
import pandas as pd

import config
import damage


def _km(lat1, lon1, lat2, lon2):
    return float(ox.distance.great_circle(lat1, lon1, lat2, lon2)) / 1000


def report(G, crossing_nodes, hub_nodes, routes, outdir, used_pairs=None):
    """used_pairs: zbiór (przejście, hub) rysowanych na mapie tras. None = wszystkie."""
    outdir.mkdir(parents=True, exist_ok=True)
    nodes, edges = ox.graph_to_gdfs(G)
    nll = nodes.to_crs(4326)
    pd.set_option("display.width", 200)

    # 1. graf
    print("\n=== 1. GRAF ===")
    print(f"węzłów {len(nodes)}, krawędzi {len(edges)}, łączna długość {edges['length'].sum() / 1000:.0f} km")
    print(f"zakres: lat {nll.geometry.y.min():.3f}..{nll.geometry.y.max():.3f}, "
          f"lon {nll.geometry.x.min():.3f}..{nll.geometry.x.max():.3f}")
    hw = edges["highway"].map(lambda h: h[0] if isinstance(h, list) else h)
    print("długość dróg wg typu [km]:")
    print((edges.groupby(hw)["length"].sum() / 1000).sort_values(ascending=False).round(0).to_string())

    # 2. przypięcia
    print("\n=== 2. PRZYPIĘCIA (zadany punkt -> najbliższy węzeł grafu) ===")
    rows = []
    for kind, pts, snapped in (("przejście", config.CROSSINGS, crossing_nodes), ("hub", config.HUBS, hub_nodes)):
        for name, (lat, lon) in pts.items():
            n = snapped[name]
            nlat, nlon = nll.loc[n].geometry.y, nll.loc[n].geometry.x
            types = {(e.get("highway")[0] if isinstance(e.get("highway"), list) else e.get("highway"))
                     for _, _, e in G.edges(n, data=True)}
            rows.append({"punkt": name, "rodzaj": kind, "odległość_m": round(_km(lat, lon, nlat, nlon) * 1000),
                         "stopień_węzła": G.out_degree(n), "typy_dróg": ",".join(sorted(map(str, types))),
                         "węzeł": n})
    snap = pd.DataFrame(rows)
    print(snap.drop(columns="węzeł").to_string(index=False))
    snap.to_csv(outdir / "diagnoza_przypiecia.csv", index=False)

    # 3. pary przejście-hub
    print("\n=== 3. TRASY: linia prosta vs graf (km) i czas przejazdu ===")
    v_free = config.TRUCK_SPEED_KMH
    rows = []
    for (c, h), r in routes.items():
        straight = _km(*config.CROSSINGS[c], *config.HUBS[h])
        # czas tej samej trasy bez zniszczeń (z uwzględnieniem wolniejszych typów dróg)
        base_min = sum(min(d["length"] / (v_free * 1000 / 60 * damage.speed_factor(d)) for d in G[a][b].values())
                       for a, b in zip(r["path"], r["path"][1:]))
        rows.append({"przejście": c, "hub": h, "linia_prosta_km": round(straight, 1),
                     "trasa/prosta": round(r["km"] / straight, 2),
                     "trasa_km": round(r["km"], 1), "czas_min": round(r["minutes"]),
                     "czas_bez_zniszczeń_min": round(base_min),
                     "spowolnienie_x": round(r["minutes"] / base_min, 1)})
    pairs = pd.DataFrame(rows)
    print(pairs.to_string(index=False))
    pairs.to_csv(outdir / "diagnoza_pary.csv", index=False)

    # 4. zniszczenia na krawędziach
    print("\n=== 4. ZNISZCZENIA NA KRAWĘDZIACH ===")
    dmg = edges["damage"]
    print("liczba punktów UNOSAT w oczku (max po krawędzi): "
          + ", ".join(f"p{q}={dmg.quantile(q / 100):.0f}" for q in (10, 25, 50, 75, 90, 99)) + f", max={dmg.max():.0f}")
    sf = edges["highway"].map(lambda h: damage.speed_factor({"highway": h}))
    slow = edges["time_min"] / (edges["length"] / (v_free * 1000 / 60 * sf))
    sat = config.TRUCK_SPEED_KMH / config.MIN_SPEED_KMH
    print(f"krawędzie bez zniszczeń: {(dmg == 0).mean():.0%}")
    print(f"czas przejazdu >= 2x: {(slow >= 2).mean():.0%}; >= 4x: {(slow >= 4).mean():.0%}; "
          f"na dolnym limicie prędkości ({config.MIN_SPEED_KMH:.0f} km/h, {sat:.0f}x): {(slow >= sat - 1e-6).mean():.0%}")

    # 5a. mapa tras: jeden kolor na przejście, wszystkie huby. Tam, gdzie trasy z różnych przejść idą tą samą drogą,
    # linie są przesunięte w bok i biegną obok siebie, więc widać każdą z nich.
    cross_colors = {"Kerem Shalom": "tab:blue", "Rafah": "tab:orange", "Erez": "tab:green", "Western Erez": "tab:red",
                    "Kissufim": "tab:purple", "Gate 96": "tab:brown", "JLOTS": "tab:pink"}
    crossings_drawn = [c for c in config.CROSSINGS if used_pairs is None or any(pc == c for pc, _ in used_pairs)]
    seg_users = {}                      # odcinek (a, b), a < b  ->  przejścia, których trasy go używają
    for (c, h), r in routes.items():
        if c not in crossings_drawn or (used_pairs is not None and (c, h) not in used_pairs):
            continue
        for u, v in zip(r["path"], r["path"][1:]):
            seg_users.setdefault((min(u, v), max(u, v)), set()).add(c)
    fig, ax = plt.subplots(figsize=(10, 11))
    edges.plot(ax=ax, color="#cccccc", linewidth=0.4)
    ax.set_axis_off()
    ax.set_title("Trasy przejście → hub (kolor = przejście)")
    step = 130                          # odstęp między liniami obok siebie [m w układzie mapy]
    segments = {c: [] for c in crossings_drawn}
    for (u, v), users in seg_users.items():
        pu, pv = nodes.loc[u].geometry, nodes.loc[v].geometry
        dx, dy = pv.x - pu.x, pv.y - pu.y
        if dx * 0.45 + dy * 0.89 < 0:   # jeden kierunek odniesienia (oś Strefy, SW -> NE), żeby przesunięcie szło po tej samej stronie drogi
            dx, dy = -dx, -dy
        norm = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / norm, dx / norm
        order = [c for c in crossings_drawn if c in users]
        for k, c in enumerate(order):
            off = (k - (len(order) - 1) / 2) * step
            segments[c].append([(pu.x + nx * off, pu.y + ny * off), (pv.x + nx * off, pv.y + ny * off)])
    for c in crossings_drawn:
        ax.add_collection(LineCollection(segments[c], colors=cross_colors.get(c, "black"), linewidths=2.2, zorder=5,
                                         label=c))
    for kind, pts, snapped, mk, col in (("przejście", config.CROSSINGS, crossing_nodes, "s", "deepskyblue"),
                                        ("hub", config.HUBS, hub_nodes, "^", "limegreen")):
        for name, (lat, lon) in pts.items():
            p = gpd_point(lon, lat, nodes.crs)
            q = nodes.loc[snapped[name]].geometry
            ax.plot([p.x, q.x], [p.y, q.y], color="red", lw=1)
            ax.scatter([p.x], [p.y], marker="x", color="red", s=40, zorder=9)
            ax.scatter([q.x], [q.y], marker=mk, color=col, edgecolor="black", s=90, zorder=10)
            ax.annotate(name, (q.x, q.y), fontsize=8, xytext=(4, 4), textcoords="offset points", zorder=11)
    ax.legend(loc="upper left", fontsize=9, title="trasy z przejścia")
    fig.tight_layout()
    fig.savefig(outdir / "diagnoza.png", dpi=160)
    plt.close(fig)

    # 5b. mapa zniszczeń: drogi pomalowane liczbą punktów UNOSAT w oczku
    fig, ax = plt.subplots(figsize=(9, 11))
    ax.set_axis_off()
    ax.set_title("Zniszczenia na krawędziach (liczba punktów UNOSAT w oczku)")
    edges.sort_values("damage").plot(ax=ax, column="damage", cmap="inferno", linewidth=0.8, legend=True,
                                     legend_kwds={"shrink": 0.5, "label": "punktów UNOSAT w oczku"})
    fig.tight_layout()
    fig.savefig(outdir / "mapa_zniszczen.png", dpi=130)
    plt.close(fig)
    print(f"\nMapy: {outdir / 'diagnoza.png'}, {outdir / 'mapa_zniszczen.png'}; tabele CSV w tym samym katalogu")


def gpd_point(lon, lat, crs):
    import geopandas as gpd
    from shapely.geometry import Point
    return gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(crs).iloc[0]
