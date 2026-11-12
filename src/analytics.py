"""analytics.py – Zaawansowana analityka i raportowanie KPI (Milestone 2).

Generuje na koniec symulacji:
  1. Tabele KPI (kolejki, czasy, pokrycie popytu, wskaźniki IPC).
  2. Identyfikację wąskich gardeł sieci drogowej (najczęściej używane krawędzie).
  3. Mapę zatorów (mapa choropleth – czas przejazdu vs. długość trasy).
  4. Wykres szeregu czasowego IPC dla każdego hubu.
  5. Raport bottleneck: ranking krawędzi i przejść granicznych wg obciążenia.

Integracja:
    reporter = analytics.Reporter(outdir, month)
    reporter.run(truck_log, demand_model, hub_edge_usage, G)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

try:
    import osmnx as ox
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False


IPC_COLORS = {1: "#1a9850", 2: "#fee08b", 3: "#fdae61", 4: "#d73027", 5: "#7b2d8b"}
IPC_LABELS = {
    1: "IPC 1 – Minimal",
    2: "IPC 2 – Stressed",
    3: "IPC 3 – Crisis",
    4: "IPC 4 – Emergency",
    5: "IPC 5 – Catastrophe",
}


class Reporter:
    """Generuje wszystkie raporty i wykresy po zakończeniu symulacji."""

    def __init__(self, outdir: Path, month: str):
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.month = month

    # ------------------------------------------------------------------
    # Główny punkt wejścia
    # ------------------------------------------------------------------
    def run(
        self,
        truck_log: pd.DataFrame,
        demand_model=None,
        hub_edge_usage: Optional[Dict] = None,
        G=None,
        crossing_closures: Optional[pd.DataFrame] = None,
    ):
        """Uruchamia cały pipeline raportowania. Zapisuje pliki do self.outdir."""
        print(f"\n=== ANALITYKA KPI [{self.month}] ===")

        kpi = self._kpi_table(truck_log)
        kpi.to_csv(self.outdir / "kpi_summary.csv")
        print("\nKPI ogólne:")
        print(kpi.to_string())

        bn = self._bottleneck_crossings(truck_log)
        bn.to_csv(self.outdir / "bottleneck_crossings.csv")
        print("\nWąskie gardła – przejścia graniczne:")
        print(bn.to_string())

        self._plot_queue_distribution(truck_log)
        self._plot_travel_time_distribution(truck_log)
        self._plot_delivery_timeline(truck_log)

        if demand_model is not None:
            history = demand_model.report()
            summary = demand_model.summary()
            if not history.empty:
                history.to_csv(self.outdir / "demand_history.csv", index=False)
                summary.to_csv(self.outdir / "demand_summary.csv", index=False)
                print("\nPodsumowanie popytu:")
                print(summary.to_string(index=False))
                self._plot_ipc_timeline(history)
                self._plot_supply_coverage(history)

        if hub_edge_usage and G is not None and HAS_OSMNX:
            bn_edges = self._bottleneck_edges(hub_edge_usage)
            bn_edges.to_csv(self.outdir / "bottleneck_edges.csv", index=False)
            self._plot_congestion_map(G, hub_edge_usage)

        print(f"\nRaporty zapisane do {self.outdir}/")

    # ------------------------------------------------------------------
    # KPI ogólne
    # ------------------------------------------------------------------
    def _kpi_table(self, log: pd.DataFrame) -> pd.DataFrame:
        total = len(log)
        delivered = log["delivered"].sum()
        rows = []

        for crossing, g in log.groupby("crossing"):
            rows.append({
                "metric": f"[{crossing}] Ciężarówek",
                "value": len(g),
            })
            rows.append({
                "metric": f"[{crossing}] Śr. czas kolejki [min]",
                "value": round(g["queue_min"].mean(), 1),
            })
            rows.append({
                "metric": f"[{crossing}] p95 czas kolejki [min]",
                "value": round(g["queue_min"].quantile(0.95), 1),
            })
            rows.append({
                "metric": f"[{crossing}] Max czas kolejki [min]",
                "value": round(g["queue_min"].max(), 1),
            })

        rows += [
            {"metric": "Łączna liczba ciężarówek", "value": total},
            {"metric": "Dowiezionych [%]", "value": round(100 * delivered / total, 1)},
            {"metric": "Niedowiezionych", "value": total - delivered},
            {"metric": "Śr. czas przejazdu [min]", "value": round(log["travel_min"].mean(), 1)},
            {"metric": "p95 czas przejazdu [min]", "value": round(log["travel_min"].quantile(0.95), 1)},
            {"metric": "Śr. długość trasy [km]", "value": round(log["route_km"].mean(), 1)},
            {"metric": "Ciężarówek ze zmianą trasy", "value": int((log["replans"] > 0).sum())},
            {"metric": "Ciężarówek czekających bez drogi", "value": int((log["stuck_min"] > 0).sum())},
            {"metric": "Łączny czas czekania bez drogi [h]",
             "value": round(log["stuck_min"].sum() / 60, 1)},
        ]
        return pd.DataFrame(rows).set_index("metric")

    def _bottleneck_crossings(self, log: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for crossing, g in log.groupby("crossing"):
            rows.append({
                "crossing": crossing,
                "trucks": len(g),
                "queue_mean_min": round(g["queue_min"].mean(), 1),
                "queue_p95_min": round(g["queue_min"].quantile(0.95), 1),
                "queue_max_min": round(g["queue_min"].max(), 1),
                "service_mean_min": round(g["service_min"].mean(), 1),
                "not_delivered": int((~g["delivered"]).sum()),
                "stuck_pct": round(100 * (g["stuck_min"] > 0).mean(), 1),
                "bottleneck_score": round(
                    g["queue_min"].quantile(0.95) * len(g) / 1000, 1
                ),  # heurystyczny wskaźnik: p95_queue * liczba ciężarówek
            })
        return (pd.DataFrame(rows)
                .sort_values("bottleneck_score", ascending=False)
                .reset_index(drop=True))

    # ------------------------------------------------------------------
    # Wąskie gardła sieci drogowej
    # ------------------------------------------------------------------
    def _bottleneck_edges(self, hub_edge_usage: dict) -> pd.DataFrame:
        rows = [
            {"u": u, "v": v, "truck_count": int(cnt)}
            for (u, v), cnt in sorted(hub_edge_usage.items(), key=lambda x: -x[1])[:50]
        ]
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Wykresy
    # ------------------------------------------------------------------
    def _plot_queue_distribution(self, log: pd.DataFrame):
        fig, axes = plt.subplots(1, len(log["crossing"].unique()),
                                 figsize=(5 * len(log["crossing"].unique()), 4),
                                 squeeze=False)
        for ax, (crossing, g) in zip(axes[0], log.groupby("crossing")):
            q = g["queue_min"]
            ax.hist(q, bins=40, color="#2171b5", edgecolor="white", linewidth=0.3)
            ax.axvline(q.mean(), color="#e31a1c", lw=1.5, linestyle="--",
                       label=f"śr. {q.mean():.0f} min")
            ax.axvline(q.quantile(0.95), color="#ff7f00", lw=1.5, linestyle=":",
                       label=f"p95 {q.quantile(0.95):.0f} min")
            ax.set_title(f"{crossing}", fontsize=11, weight="bold")
            ax.set_xlabel("Czas oczekiwania w kolejce [min]")
            ax.set_ylabel("Liczba ciężarówek")
            ax.legend(fontsize=8)
        fig.suptitle("Rozkład czasu oczekiwania na przejściach granicznych", weight="bold")
        fig.tight_layout()
        fig.savefig(self.outdir / "kpi_queue_dist.png", dpi=130)
        plt.close(fig)

    def _plot_travel_time_distribution(self, log: pd.DataFrame):
        delivered = log[log["delivered"]]
        if delivered.empty:
            return
        fig, ax = plt.subplots(figsize=(8, 4))
        for hub, g in delivered.groupby("hub"):
            ax.hist(g["travel_min"], bins=30, alpha=0.6, label=hub, edgecolor="white", lw=0.2)
        ax.set_xlabel("Czas przejazdu do hubu [min]")
        ax.set_ylabel("Liczba ciężarówek")
        ax.set_title("Rozkład czasu przejazdu wg hubu docelowego", weight="bold")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(self.outdir / "kpi_travel_dist.png", dpi=130)
        plt.close(fig)

    def _plot_delivery_timeline(self, log: pd.DataFrame):
        """Liczba dostaw dziennie (dowiezione / niedowiezione) – wykres słupkowy."""
        log2 = log.copy()
        log2["day"] = (log2["arrival_min"] // 1440).astype(int) + 1
        daily = log2.groupby(["day", "delivered"]).size().unstack(fill_value=0)
        daily.columns = ["Niedowiezione" if not c else "Dowiezione" for c in daily.columns]

        fig, ax = plt.subplots(figsize=(10, 4))
        bottom = np.zeros(len(daily))
        colors = {"Dowiezione": "#2ca02c", "Niedowiezione": "#d62728"}
        for col in ["Dowiezione", "Niedowiezione"]:
            if col in daily.columns:
                ax.bar(daily.index, daily[col], bottom=bottom,
                       label=col, color=colors[col], width=0.8)
                bottom += daily[col].values
        ax.set_xlabel("Dzień miesiąca")
        ax.set_ylabel("Liczba ciężarówek")
        ax.set_title("Dzienny strumień dostaw", weight="bold")
        ax.legend()
        fig.tight_layout()
        fig.savefig(self.outdir / "kpi_delivery_timeline.png", dpi=130)
        plt.close(fig)

    def _plot_ipc_timeline(self, history: pd.DataFrame):
        """Linia IPC dla każdego hubu przez cały miesiąc."""
        hubs = history["hub"].unique()
        fig, ax = plt.subplots(figsize=(11, 5))
        for hub in hubs:
            sub = history[history["hub"] == hub].sort_values("day")
            ax.plot(sub["day"], sub["ipc_phase"], marker="o", ms=4, label=hub)

        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_yticklabels([IPC_LABELS[i] for i in range(1, 6)], fontsize=8)
        ax.set_ylim(0.5, 5.5)
        ax.invert_yaxis()  # IPC 1 na górze = dobry stan
        ax.set_xlabel("Dzień miesiąca")
        ax.set_title("Faza IPC – bezpieczeństwo żywnościowe wg hubu", weight="bold")
        ax.legend(fontsize=8)

        # Kolorowe pasy tła wg faz IPC
        for phase, color in IPC_COLORS.items():
            ax.axhspan(phase - 0.5, phase + 0.5, alpha=0.08, color=color, lw=0)

        fig.tight_layout()
        fig.savefig(self.outdir / "kpi_ipc_timeline.png", dpi=130)
        plt.close(fig)

    def _plot_supply_coverage(self, history: pd.DataFrame):
        """Zapasy żywności i wody wg hubu (dobowy poziom na tle zapotrzebowania)."""
        hubs = history["hub"].unique()
        fig, axes = plt.subplots(2, len(hubs), figsize=(4 * len(hubs), 6), squeeze=False)

        for col, (ax_row, metric, label, color) in enumerate([
            (axes[0], "stock_food_mt", "Zapas żywności [t]", "#1f77b4"),
            (axes[1], "stock_water_mt", "Zapas wody [t]", "#17becf"),
        ]):
            for ax, hub in zip(ax_row, hubs):
                sub = history[history["hub"] == hub].sort_values("day")
                ax.fill_between(sub["day"], sub[metric], alpha=0.4, color=color)
                ax.plot(sub["day"], sub[metric], color=color, lw=1.5)
                ax.set_title(f"{hub.replace('Hub_', '')}", fontsize=9, weight="bold")
                ax.set_xlabel("Dzień")
                ax.set_ylabel(label, fontsize=8)

        fig.suptitle("Poziom zapasów w hubах – żywność i woda", weight="bold")
        fig.tight_layout()
        fig.savefig(self.outdir / "kpi_supply_coverage.png", dpi=130)
        plt.close(fig)

    def _plot_congestion_map(self, G, hub_edge_usage: dict):
        """Mapa zatorów: krawędzie pomalowane wg liczby przejeżdżających ciężarówek."""
        if not HAS_OSMNX:
            return
        nodes, edges = ox.graph_to_gdfs(G)
        edge_counts = pd.Series({
            (min(u, v), max(u, v)): cnt
            for (u, v), cnt in hub_edge_usage.items()
        })
        edge_key = edges.index.map(lambda idx: (min(idx[0], idx[1]), max(idx[0], idx[1])))
        edges = edges.copy()
        edges["usage"] = edge_key.map(edge_counts).fillna(0)

        fig, ax = plt.subplots(figsize=(9, 11))
        ax.set_axis_off()
        edges[edges["usage"] == 0].plot(ax=ax, color="#dddddd", linewidth=0.3)
        edges[edges["usage"] > 0].sort_values("usage").plot(
            ax=ax, column="usage", cmap="YlOrRd", linewidth=1.5, legend=True,
            legend_kwds={"shrink": 0.5, "label": "Liczba przejeżdżających ciężarówek"},
        )
        ax.set_title("Mapa zatorów – obciążenie sieci drogowej", weight="bold")
        fig.tight_layout()
        fig.savefig(self.outdir / "kpi_congestion_map.png", dpi=130)
        plt.close(fig)
