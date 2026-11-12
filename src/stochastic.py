"""stochastic.py – Losowe zdarzenia zakłócające (opcjonalna warstwa, flaga --stochastic).

Generuje zdarzenia events.Event dla:
  1. losowych krótkotrwałych zamknięć dróg (incydenty, kontrole wojskowe itp.),
  2. losowego zamknięcia przejścia granicznego na kilka godzin,
oraz losuje awarie ciężarówek w trasie (sample_breakdown, wołane z sim.py).

Wszystkie parametry są w config.py (sekcja Milestone 2) i oznaczone ZAŁOŻENIE (brak danych kalibracyjnych).
Losowania idą z osobnego generatora, więc włączenie zdarzeń nie zmienia losowań ciężarówek (przyjazdy, odprawa, hub).

Zamknięte przejścia trzyma obiekt (zbiór nazw) przekazany z run.py do sim.py, a nie zmienna globalna,
więc kolejne przebiegi (multi-seed) nie mają wspólnego stanu.
"""
from __future__ import annotations

import math
from typing import List, Set

import numpy as np

import config
from events import Event


def _duration_minutes(mean_h: float, std_h: float, rng: np.random.Generator) -> float:
    """Czas trwania zdarzenia [min] z uciętego rozkładu normalnego (min. 30 min)."""
    return max(0.5, rng.normal(mean_h, std_h)) * 60


def _edge_blocker(u, v, delta):
    def apply(G_, dm_):
        if G_.has_edge(u, v):
            for d in G_[u][v].values():
                d["blocked"] = max(0, d.get("blocked", 0) + delta)
        return {(u, v)}
    return apply


def generate_road_incidents(G, month_days: int, rng: np.random.Generator,
                            busy_edges: List[tuple] | None = None) -> List[Event]:
    """Losowe krótkotrwałe zamknięcia pojedynczych krawędzi (jeden kierunek).

    busy_edges: lista ((u, v), liczba ciężarówek) malejąco wg ruchu (events.busiest_edges). Pierwsze
    config.INCIDENT_BUSY_TOP_K krawędzi ma INCIDENT_BUSY_FACTOR razy większe ryzyko.
    """
    edges = list(G.edges(keys=False))
    if not edges:
        return []
    busy = set()
    for (u, v), _ in (busy_edges or [])[:config.INCIDENT_BUSY_TOP_K]:
        busy.add((u, v))
        busy.add((v, u))
    rate = np.full(len(edges), config.INCIDENT_RATE_PER_EDGE_PER_DAY)
    rate[[i for i, e in enumerate(edges) if e in busy]] *= config.INCIDENT_BUSY_FACTOR

    events: List[Event] = []
    for day in range(month_days):
        for i in np.nonzero(rng.random(len(edges)) < rate)[0]:
            u, v = edges[i]
            start = day * 1440 + rng.uniform(0, 1440)
            dur = _duration_minutes(config.INCIDENT_DURATION_HOURS_MEAN, config.INCIDENT_DURATION_HOURS_STD, rng)
            events.append(Event(start, f"INCYDENT: krawędź ({u},{v}) zamknięta na {dur / 60:.1f} h",
                                _edge_blocker(u, v, +1)))
            events.append(Event(start + dur, f"KONIEC INCYDENTU: krawędź ({u},{v}) otwarta",
                                _edge_blocker(u, v, -1)))
    return events


def generate_crossing_closures(crossing_nodes: dict, month_days: int, rng: np.random.Generator,
                               closed: Set[str]) -> List[Event]:
    """Losowe zamknięcia przejść granicznych. Zdarzenie dodaje nazwę przejścia do zbioru `closed`
    (i usuwa po otwarciu); sim.py czeka z wjazdem ciężarówki, dopóki jej przejście jest w tym zbiorze."""
    def make(c, add):
        def apply(G_, dm_):
            (closed.add if add else closed.discard)(c)
            return set()
        return apply

    events: List[Event] = []
    for crossing, rate in config.CROSSING_CLOSURE_RATE_PER_DAY.items():
        if crossing not in crossing_nodes:
            continue
        for day in range(month_days):
            if rng.random() > rate:
                continue
            start = day * 1440 + rng.uniform(360, 900)   # między 6:00 a 15:00
            dur = _duration_minutes(config.CROSSING_CLOSURE_HOURS_MEAN, config.CROSSING_CLOSURE_HOURS_STD, rng)
            events.append(Event(start, f"ZAMKNIĘCIE przejścia {crossing} na {dur / 60:.1f} h",
                                make(crossing, True), roads=False))
            events.append(Event(start + dur, f"OTWARCIE przejścia {crossing}", make(crossing, False), roads=False))
    return events


def sample_breakdown(route_km: float, rng: np.random.Generator) -> float:
    """Dodatkowe opóźnienie [min] z powodu awarii pojazdu na trasie o długości route_km (0, gdy bez awarii).
    Czas naprawy log-normalny (długi ogon: rzadko poważna usterka)."""
    prob = 1 - (1 - config.BREAKDOWN_PROB_PER_100KM / 100) ** route_km
    if rng.random() > prob:
        return 0.0
    m, s = config.BREAKDOWN_REPAIR_MIN_MEAN, config.BREAKDOWN_REPAIR_MIN_STD
    sigma2 = math.log(1 + (s / m) ** 2)
    return float(rng.lognormal(math.log(m) - sigma2 / 2, math.sqrt(sigma2)))
