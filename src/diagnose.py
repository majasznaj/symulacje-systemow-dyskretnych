"""Diagnostyka grafu dróg, przypięcia punktów i zniszczeń: python src/run.py --diagnose"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

import config
import damage


def _km(lat1, lon1, lat2, lon2):
    return float(ox.distance.great_circle(lat1, lon1, lat2, lon2)) / 1000


def report(G, crossing_nodes, hub_nodes, routes, outdir):
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
                     "najkrótsza_km": round(r["shortest_km"], 1),
                     "najkr/prosta": round(r["shortest_km"] / straight, 2),
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
    print("koszt routera = czas (RISK_WEIGHT=%g)" % config.RISK_WEIGHT)

    # 5. mapa: lewo = graf, przypięcia i trasy; prawo = zniszczenia na krawędziach
    fig, axes = plt.subplots(1, 2, figsize=(16, 11))
    for ax in axes:
        edges.plot(ax=ax, color="#bbbbbb", linewidth=0.4)
        ax.set_axis_off()
    ax = axes[0]
    ax.set_title("Graf, przypięcia (linie od punktu zadanego do węzła) i trasy")
    for kind, pts, snapped, mk, col in (("przejście", config.CROSSINGS, crossing_nodes, "s", "deepskyblue"),
                                        ("hub", config.HUBS, hub_nodes, "^", "limegreen")):
        for name, (lat, lon) in pts.items():
            p = gpd_point(lon, lat, nodes.crs)
            q = nodes.loc[snapped[name]].geometry
            ax.plot([p.x, q.x], [p.y, q.y], color="red", lw=1)
            ax.scatter([p.x], [p.y], marker="x", color="red", s=40, zorder=9)
            ax.scatter([q.x], [q.y], marker=mk, color=col, edgecolor="black", s=90, zorder=10)
            ax.annotate(name, (q.x, q.y), fontsize=8, xytext=(4, 4), textcoords="offset points")
    route_colors = {
        ("Kerem Shalom", "Hub_Rafah"): "orange",
        ("Rafah", "Hub_Khan_Younis"): "magenta",
        ("Gate 96", "Hub_Deir_al_Balah"): "cyan",
        ("Erez", "Hub_North_Jabalia"): "lime",
        ("Western Erez", "Hub_Gaza_City"): "red",
        ("Kerem Shalom", "Hub_North_Jabalia"): "yellow",
    }
    for (c, h), color in route_colors.items():
        if (c, h) in routes:
            path = routes[(c, h)]["path"]
            xs = [nodes.loc[n].geometry.x for n in path]
            ys = [nodes.loc[n].geometry.y for n in path]
            ax.plot(xs, ys, color=color, lw=2.5, label=f"{c} -> {h}")
    ax.legend(loc="upper left")
    ax = axes[1]
    ax.set_title("Zniszczenia na krawędziach (liczba punktów UNOSAT w oczku)")
    e = edges.sort_values("damage")
    e.plot(ax=ax, column="damage", cmap="inferno", linewidth=0.8, legend=True,
           legend_kwds={"shrink": 0.5, "label": "punktów UNOSAT w oczku"})
    fig.tight_layout()
    fig.savefig(outdir / "diagnoza.png", dpi=110)
    plt.close(fig)
    print(f"\nMapa: {outdir / 'diagnoza.png'}; tabele CSV w tym samym katalogu")


def gpd_point(lon, lat, crs):
    import geopandas as gpd
    from shapely.geometry import Point
    return gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(crs).iloc[0]
