"""stochastic.py – Losowe zdarzenia zakłócające (Milestone 2).

Generuje zdarzenia events.Event dla:
  1. Losowych krótkotrwałych zamknięć dróg (incydenty, kontrole wojskowe itp.)
  2. Awarii ciężarówek w trasie (modelowane jako dodatkowe opóźnienie w sim.py)
  3. Losowego zamknięcia przejścia granicznego na kilka godzin

Wszystkie rozkłady są parametryzowane w config.py (sekcja STOCHASTIC).
Oznaczone ZAŁOŻENIE – brak danych kalibracyjnych, opisać w raporcie.

Integracja:
    events_list += stochastic.generate_road_incidents(G, routes, rng, month_days)
    # awarie pojazdów: obsługiwane przez sim.py przez losowanie z rng przy starcie trasy
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import pandas as pd

import config
from events import Event

INF = math.inf

# ---------------------------------------------------------------------------
# Domyślne parametry stochastyczne (można nadpisać w config.py)
# ---------------------------------------------------------------------------
# Wszystkie oznaczone ZAŁOŻENIE
INCIDENT_RATE_PER_EDGE_PER_DAY = getattr(config, "INCIDENT_RATE_PER_EDGE_PER_DAY", 0.002)
# Prawdopodobieństwo incydentu na jednej krawędzi przez jeden dzień. Przy ~8000 krawędzi
# daje ~16 incydentów/dzień; w rzeczywistości incydenty skupiają się na głównych arteriach.

INCIDENT_DURATION_HOURS_MEAN = getattr(config, "INCIDENT_DURATION_HOURS_MEAN", 3.0)
INCIDENT_DURATION_HOURS_STD = getattr(config, "INCIDENT_DURATION_HOURS_STD", 1.5)

CROSSING_CLOSURE_RATE_PER_DAY = getattr(config, "CROSSING_CLOSURE_RATE_PER_DAY", {
    "Kerem Shalom": 0.15,   # ZAŁOŻENIE: ~4-5 zamknięć w miesiącu
    "Rafah": 0.20,          # ZAŁOŻENIE: wyższe ze względu na konflikty
})
CROSSING_CLOSURE_HOURS_MEAN = getattr(config, "CROSSING_CLOSURE_HOURS_MEAN", 6.0)
CROSSING_CLOSURE_HOURS_STD = getattr(config, "CROSSING_CLOSURE_HOURS_STD", 2.0)

# Awarie pojazdów: prawdopodobieństwo awarii na 100 km trasy (ZAŁOŻENIE)
BREAKDOWN_PROB_PER_100KM = getattr(config, "BREAKDOWN_PROB_PER_100KM", 0.03)
# Czas naprawy [min] – rozkład log-normalny (ZAŁOŻENIE)
BREAKDOWN_REPAIR_MIN_MEAN = getattr(config, "BREAKDOWN_REPAIR_MIN_MEAN", 90.0)
BREAKDOWN_REPAIR_MIN_STD = getattr(config, "BREAKDOWN_REPAIR_MIN_STD", 60.0)


def _duration_minutes(mean_h: float, std_h: float, rng: np.random.Generator) -> float:
    """Losuje czas trwania zdarzenia [min] z uciętego rozkładu normalnego."""
    duration_h = max(0.5, rng.normal(mean_h, std_h))
    return duration_h * 60


def generate_road_incidents(
    G,
    month_days: int,
    rng: np.random.Generator,
    busy_edges: List[tuple] | None = None,
    top_k_busy: int = 200,
) -> List[Event]:
    """Generuje losowe krótkotrwałe zamknięcia krawędzi grafu.

    busy_edges (opcjonalnie): lista (u, v) posortowana malejąco według ruchu.
    Jeśli podana, incydenty skupiają się na top_k_busy krawędziach z wyższą wagą.
    """
    events: List[Event] = []
    all_edges = list(G.edges(keys=False))
    if not all_edges:
        return events

    # Wyodrębnij uczęszczane krawędzie dla wyższego prawdopodobieństwa incydentów
    busy_set = set()
    if busy_edges:
        for (u, v), _ in busy_edges[:top_k_busy]:
            busy_set.add((u, v))
            busy_set.add((v, u))

    for day in range(month_days):
        for (u, v) in all_edges:
            rate = INCIDENT_RATE_PER_EDGE_PER_DAY
            if (u, v) in busy_set:
                rate *= 3.0   # uczęszczane drogi mają 3x wyższe ryzyko incydentu

            if rng.random() > rate:
                continue

            # Moment incydentu: losowy czas w ciągu dnia
            minute = day * 1440 + rng.uniform(0, 1440)
            duration = _duration_minutes(
                INCIDENT_DURATION_HOURS_MEAN, INCIDENT_DURATION_HOURS_STD, rng
            )

            label_close = f"INCYDENT: krawędź ({u},{v}) zamknięta na {duration / 60:.1f} h"
            label_open = f"KONIEC INCYDENTU: krawędź ({u},{v}) otwarta"

            # Domknięcia (blokada jednego kierunku)
            def make_close(uu, vv):
                def close(G_, dm_):
                    if G_.has_edge(uu, vv):
                        for d in G_[uu][vv].values():
                            d["blocked"] = d.get("blocked", 0) + 1
                    return {(uu, vv)}
                return close

            def make_open(uu, vv):
                def reopen(G_, dm_):
                    if G_.has_edge(uu, vv):
                        for d in G_[uu][vv].values():
                            d["blocked"] = max(0, d.get("blocked", 0) - 1)
                    return {(uu, vv)}
                return reopen

            events.append(Event(minute, label_close, make_close(u, v)))
            events.append(Event(minute + duration, label_open, make_open(u, v)))

    return events


def generate_crossing_closures(
    crossing_nodes: dict,
    month_days: int,
    rng: np.random.Generator,
) -> List[Event]:
    """Generuje losowe zamknięcia przejść granicznych.

    Zwraca zdarzenia zmieniające config.LANES na 0 (brak stanowisk = de facto zamknięcie).
    W sim.py kolejka na zamkniętym przejściu staje; ciężarówki czekają i wznowią po otwarciu.
    """
    events: List[Event] = []
    for crossing, rate in CROSSING_CLOSURE_RATE_PER_DAY.items():
        for day in range(month_days):
            if rng.random() > rate:
                continue
            minute = day * 1440 + rng.uniform(360, 900)  # między 6:00 a 15:00
            duration = _duration_minutes(
                CROSSING_CLOSURE_HOURS_MEAN, CROSSING_CLOSURE_HOURS_STD, rng
            )
            label_close = f"ZAMKNIĘCIE przejścia {crossing} na {duration / 60:.1f} h"
            label_open = f"OTWARCIE przejścia {crossing}"

            def make_close_crossing(c):
                def close(G_, dm_):
                    # Oznaczamy przejście jako zamknięte w danych globalnych
                    if not hasattr(close, "_registry"):
                        close._registry = {}
                    close._registry[c] = True
                    return set()
                return close

            def make_open_crossing(c):
                def reopen(G_, dm_):
                    if hasattr(make_close_crossing(c), "_registry"):
                        make_close_crossing(c)._registry.pop(c, None)
                    return set()
                return reopen

            # Zamiast modyfikować graf, odnotowujemy zdarzenie w logzie
            # (sim.py czyta CLOSED_CROSSINGS ze stanu globalnego)
            events.append(Event(minute, label_close, _make_crossing_close(crossing)))
            events.append(Event(minute + duration, label_open, _make_crossing_open(crossing)))

    return events


# Globalny rejestr zamkniętych przejść (odczytywany przez sim.py)
CLOSED_CROSSINGS: set = set()


def _make_crossing_close(crossing: str):
    def apply(G_, dm_):
        CLOSED_CROSSINGS.add(crossing)
        return set()
    return apply


def _make_crossing_open(crossing: str):
    def apply(G_, dm_):
        CLOSED_CROSSINGS.discard(crossing)
        return set()
    return apply


def sample_breakdown(route_km: float, rng: np.random.Generator) -> float:
    """Zwraca losowy czas dodatkowego opóźnienia [min] z powodu awarii pojazdu.

    Wywołaj przed startem trasy w sim.py. Zwraca 0.0, jeśli brak awarii.
    Czas awarii losowany z log-normalnego (długi ogon – rzadko poważna usterka).
    """
    prob = 1 - (1 - BREAKDOWN_PROB_PER_100KM / 100) ** route_km
    if rng.random() > prob:
        return 0.0
    # log-normal: wyznaczamy parametry z mean i std
    m, s = BREAKDOWN_REPAIR_MIN_MEAN, BREAKDOWN_REPAIR_MIN_STD
    sigma2 = math.log(1 + (s / m) ** 2)
    mu = math.log(m) - sigma2 / 2
    return float(rng.lognormal(mu, math.sqrt(sigma2)))
