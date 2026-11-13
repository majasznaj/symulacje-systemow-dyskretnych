"""Zdarzenia zmieniające drogi w czasie symulacji: fale zniszczeń UNOSAT i blokady dróg."""
from dataclasses import dataclass
from typing import Callable

import pandas as pd

import config
import damage


@dataclass
class Event:
    minute: float          # minuty od początku miesiąca
    label: str
    apply: Callable        # apply(G, damage_model) -> zbiór par (u, v), których koszt się zmienił
    roads: bool = True     # False: zdarzenie nie zmienia dróg (np. zamknięcie przejścia), router nie jest przeliczany


def _both_directions(G, edges):
    uv = set()
    for u, v in edges:
        if G.has_edge(u, v):
            uv.add((u, v))
        if G.has_edge(v, u):
            uv.add((v, u))
    return uv


def blockade_events(G, minute, hours, edges, label):
    """Zamknięcie dróg (oba kierunki) na dany czas. Zwraca dwa zdarzenia: zamknięcie i otwarcie."""
    uv = _both_directions(G, edges)

    def close(G_, dm):
        for u, v in uv:
            for d in G_[u][v].values():
                d["blocked"] = d.get("blocked", 0) + 1
        return set(uv)

    def reopen(G_, dm):
        for u, v in uv:
            for d in G_[u][v].values():
                d["blocked"] = max(0, d.get("blocked", 0) - 1)
        return set(uv)

    return [Event(minute, f"BLOKADA: {label} ({len(uv)} krawędzi) na {hours:g} h", close),
            Event(minute + hours * 60, f"KONIEC BLOKADY: {label}", reopen)]


def busiest_edges(routes, pair_weights, k=1):
    """k najbardziej uczęszczanych krawędzi (bez rozróżniania kierunku) według planowanych tras.

    pair_weights = {(przejście, hub): oczekiwana liczba ciężarówek}. Zwraca listę ((u, v), liczba ciężarówek).
    """
    use = {}
    for pair, r in routes.items():
        w = pair_weights.get(pair, 0)
        for a, b in zip(r["path"][:-1], r["path"][1:]):
            key = (min(a, b), max(a, b))
            use[key] = use.get(key, 0) + w
    return sorted(use.items(), key=lambda kv: -kv[1])[:k]


def unosat_wave_events(dm, gdf, month_start, next_month_start):
    """Nowe punkty UNOSAT wchodzą w dniu zdjęcia, a znikają po losowym czasie odgruzowania (kolumna expires)."""
    first, expires = gdf["first"], gdf["expires"]
    events = []
    added = (first > month_start) & (first < next_month_start)
    for date in sorted(first[added].unique()):
        sub = gdf[(first == date).to_numpy()]
        minute = (pd.Timestamp(date) - month_start).total_seconds() / 60
        label = f"FALA UNOSAT {pd.Timestamp(date).date()}: +{len(sub)} punktów zniszczeń"
        events.append(Event(minute, label, lambda G_, dm_, sub=sub: dm_.add_points(sub)))
    # odgruzowanie: punkty widoczne w tym miesiącu, które schodzą przed jego końcem (po dobie, żeby było mało zdarzeń)
    cleared = first.notna() & (first < next_month_start) & (expires > month_start) & (expires < next_month_start)
    day = expires.dt.floor("D")
    for date in sorted(day[cleared].unique()):
        sub = gdf[(cleared & (day == date)).to_numpy()]
        minute = max(0.0, (pd.Timestamp(date) - month_start).total_seconds() / 60)
        label = f"ODGRUZOWANIE {pd.Timestamp(date).date()}: -{len(sub)} punktów"
        events.append(Event(minute, label, lambda G_, dm_, sub=sub: dm_.remove_points(sub)))
    return events
