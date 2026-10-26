"""Krok 7: tabele podsumowujące i trzy wykresy z kryteriów zaliczenia M1."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config


def summarize(log):
    done = log[log["delivered"]]
    q = log.groupby("crossing").agg(
        trucks=("truck_id", "size"), queue_mean_min=("queue_min", "mean"),
        queue_p95_min=("queue_min", lambda s: s.quantile(0.95)), queue_max_min=("queue_min", "max"),
    )
    h = done.groupby("hub").agg(
        trucks=("truck_id", "size"), route_km_mean=("route_km", "mean"),
        detour_km_mean=("detour_km", "mean"), travel_min_mean=("travel_min", "mean"),
        travel_min_p95=("travel_min", lambda s: s.quantile(0.95)),
    )
    return q.round(1), h.round(1)


def _max_concurrent(starts, ends):
    """Największa liczba jednocześnie zajętych stanowisk (przedziały [start, koniec))."""
    ev = sorted([(t, 1) for t in starts] + [(t, -1) for t in ends], key=lambda x: (x[0], x[1]))
    cur = best = 0
    for _, d in ev:
        cur += d
        best = max(best, cur)
    return best


def checks(trucks, log):
    """Testy, które mogą wyjść na nie. Zwraca listę (opis, zaliczone).

    Dzienne wjazdy w symulacji pochodzą wprost z dat w Excelu, więc porównanie ich z Excelem
    niczego nie sprawdzało i zostało usunięte. Sprawdzamy to, co robi SimPy: stanowiska i kolejki.
    """
    res = [("symulacja obsłużyła wszystkie ciężarówki z Excela", len(log) == len(trucks) and log["truck_id"].is_unique)]
    start_service = log["arrival_min"] + log["queue_min"]
    res.append(("czasy kolejek są nieujemne, a dojazd kończy się po odprawie",
                bool((log["queue_min"] >= -1e-9).all() and (log["done_min"] >= log["cleared_min"] - 1e-9).all())))
    ok = True
    for c, g in log.groupby("crossing"):
        peak = _max_concurrent(start_service[g.index], g["cleared_min"])
        ok &= peak <= config.LANES.get(c, config.DEFAULT_LANES)
    res.append(("na żadnym przejściu nie obsługiwano naraz więcej ciężarówek niż stanowisk", bool(ok)))
    last_queue = log.sort_values("cleared_min").groupby("crossing").tail(50).groupby("crossing")["queue_min"].mean()
    res.append(("kolejki nie rosną bez końca (ostatnie 50 ciężarówek na przejściu czeka < 60 min)",
                bool((last_queue < 60).all())))
    res.append((f"wszystkie ciężarówki dowiozły ładunek (niedowiezione: {int((~log['delivered']).sum())})",
                bool(log["delivered"].all())))
    return res


def make_plots(trucks, log, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    start = log["date"].min().normalize()

    # 1. ciężarówki na dzień: dane (wjazdy) vs symulacja (zakończona odprawa)
    fig, ax = plt.subplots(figsize=(10, 4))
    data = trucks.groupby("date").size()
    sim_day = (start + pd.to_timedelta((log["cleared_min"] // 1440), unit="D")).value_counts().sort_index()
    ax.plot(data.index, data.values, label="dane (Excel, wjazdy)", lw=2)
    ax.plot(sim_day.index, sim_day.values, "--", label="symulacja (koniec odprawy)", lw=2)
    ax.set_ylabel("ciężarówek na dzień")
    ax.legend()
    ax.set_title("Kontrola: wjazdy z Excela = zakończone odprawy w symulacji (linie mają się pokrywać)")
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(outdir / "1_ciezarowki_na_dzien.png", dpi=130); plt.close(fig)

    # 2. czas w kolejce na przejściach
    fig, ax = plt.subplots(figsize=(8, 4))
    groups = [(c, g["queue_min"].to_numpy()) for c, g in log.groupby("crossing")]
    ax.boxplot([g for _, g in groups], showfliers=False)
    ax.set_xticklabels([f"{c}\n(n={len(g)})" for c, g in groups])
    ax.set_ylabel("czas w kolejce [min]")
    ax.set_title("Czas oczekiwania na przejściu (założenia: liczba stanowisk i czas odprawy)")
    fig.tight_layout(); fig.savefig(outdir / "2_czas_w_kolejce.png", dpi=130); plt.close(fig)

    # 3. czas przejazdu do hubu
    fig, ax = plt.subplots(figsize=(8, 4))
    groups = [(h, g["travel_min"].to_numpy()) for h, g in log[log["delivered"]].groupby("hub")]
    ax.boxplot([g for _, g in groups], showfliers=False)
    ax.set_xticklabels([f"{h.replace('Hub_', '')}\n(n={len(g)})" for h, g in groups])
    ax.set_ylabel("czas przejazdu [min]")
    ax.set_title("Czas przejazdu od przejścia do hubu")
    fig.tight_layout(); fig.savefig(outdir / "3_czas_przejazdu.png", dpi=130); plt.close(fig)
