"""demand.py – Warstwa popytowa i wskaźnik bezpieczeństwa żywnościowego (Milestone 2, autor: Martyna; zintegrowane).

Każdy hub obsługuje pewną populację (data.hub_population: config.GAZA_POPULATION razy udział hubu w wydaniach miesiąca) i ma dzienne zapotrzebowanie na żywność.
Dostawy zwiększają zapas w hubie, a co dobę populacja zjada tyle, ile jest w zapasie (do pełnej racji).
Faza bezpieczeństwa żywnościowego jest liczona z kalorii faktycznie zjedzonych tego dnia na osobę.

UWAGA: faza 1–5 jest UPROSZCZONA i tylko wzorowana na skali IPC (oficjalne IPC łączy wiele wskaźników, m.in. ceny,
śmiertelność i odżywienie dzieci). Nie nazywamy jej w raporcie "IPC", tylko wskaźnikiem pokrycia kalorii. Wody nie ma,
bo w danych ONZ nie ma kategorii wody (Cargo Category: Food, Non-Food, Mixed, Medical).

Integracja z sim.py (robi to sim.run_simulation, gdy podamy demand_model):
  - DemandModel.deliver(hub, minute, cargo_category, quantity_mt) przy każdym rozładunku,
  - DemandModel.daily_tick(day) co 1440 min,
  - DemandModel.report() / summary() po symulacji.
"""
from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd

import config

# Stałe żywieniowe (FAO/WFP, wartości orientacyjne)
KCAL_PER_MT_FOOD = 3_300_000   # kcal w 1 tonie żywności (uśrednione, ZAŁOŻENIE)
KCAL_MIN_SURVIVAL = 1_500      # kcal/osobę/dzień – granica przeżycia
KCAL_ADEQUATE = 2_100          # kcal/osobę/dzień – pełne pokrycie potrzeb

# Cargo Category z Commodities-Received -> typ towaru w modelu
CARGO_TYPE = {
    "Food Items": "food",
    "Medical Supplies": "medical",
    "Non-Food Items": "other",
    "Mixed Items": "other",     # mieszany ładunek: nie liczymy go jako żywności (zaniża pokrycie)
}


def estimate_mt(quantity, unit):
    """Masa ładunku jednej ciężarówki [t] z ilości i jednostki (patrz config.TONNES_PER_PALLET)."""
    try:
        q = float(quantity)
    except (TypeError, ValueError):
        q = float("nan")
    u = str(unit).strip().lower()
    if q != q or q <= 0:
        mt = config.TRUCK_PAYLOAD_MT
    elif u in ("mt", "ton", "tons", "tonne", "tonnes"):
        mt = q
    elif u == "pallets":
        mt = q * config.TONNES_PER_PALLET
    elif u == "truck":
        mt = q * config.TRUCK_PAYLOAD_MT
    else:   # sztuki, namioty, kartony: brak wagi
        mt = config.TRUCK_PAYLOAD_MT
    return min(max(mt, 0.1), config.MAX_TRUCK_MT)


def food_phase(kcal_per_capita: float) -> int:
    """Uproszczona faza 1–5 (wzorowana na IPC) z kalorii zjedzonych na osobę w ciągu doby."""
    if kcal_per_capita >= KCAL_ADEQUATE:
        return 1   # minimalna
    if kcal_per_capita >= 1_900:
        return 2   # napięta
    if kcal_per_capita >= 1_700:
        return 3   # kryzys
    if kcal_per_capita >= KCAL_MIN_SURVIVAL:
        return 4   # zagrożenie
    return 5       # katastrofa


@dataclass
class HubDemand:
    """Stan zapotrzebowania i zapasów dla jednego hubu."""
    name: str
    population: int

    stock_food_mt: float = 0.0
    stock_medical_mt: float = 0.0

    total_delivered_food: float = 0.0
    total_consumed_food: float = 0.0
    total_need_food: float = 0.0
    last_intake_kcal: float = 0.0     # kcal/osobę zjedzone w ostatniej dobie

    history: List[dict] = field(default_factory=list)

    @property
    def daily_food_need_mt(self) -> float:
        return self.population * KCAL_ADEQUATE / KCAL_PER_MT_FOOD

    def phase(self) -> int:
        return food_phase(self.last_intake_kcal)

    def consume_daily(self, day: int):
        """Populacja zjada dobową rację z zapasu. Brak zapasu = niezaspokojony popyt."""
        need = self.daily_food_need_mt
        consumed = min(self.stock_food_mt, need)
        self.stock_food_mt -= consumed
        self.total_consumed_food += consumed
        self.total_need_food += need
        self.last_intake_kcal = consumed * KCAL_PER_MT_FOOD / self.population if self.population else 0.0
        self.history.append({
            "day": day,
            "hub": self.name,
            "population": self.population,
            "food_need_mt": round(need, 2),
            "food_consumed_mt": round(consumed, 2),
            "stock_food_mt": round(self.stock_food_mt, 2),
            "kcal_per_capita": round(self.last_intake_kcal, 0),
            "ipc_phase": self.phase(),
            "unmet_food_mt_cum": round(self.total_need_food - self.total_consumed_food, 2),
        })


class DemandModel:
    """Zarządza stanem popytowym wszystkich hubów przez całą symulację."""

    def __init__(self, populations: Dict[str, int]):
        """populations: {hub: liczba mieszkańców}, patrz data.hub_population()."""
        pops = populations
        self.hubs: Dict[str, HubDemand] = {name: HubDemand(name=name, population=pop) for name, pop in pops.items()}

    def deliver(self, hub: str, minute: float, cargo_category: str, quantity_mt: float):
        """Rejestruje dostawę [tony] do danego hubu."""
        hd = self.hubs.get(hub)
        if hd is None:
            return
        kind = CARGO_TYPE.get(cargo_category, "other")
        if kind == "food":
            hd.stock_food_mt += quantity_mt
            hd.total_delivered_food += quantity_mt
        elif kind == "medical":
            hd.stock_medical_mt += quantity_mt

    def daily_tick(self, day: int):
        for hd in self.hubs.values():
            hd.consume_daily(day)

    def snapshot(self) -> Dict[str, dict]:
        """Bieżący stan hubów (do logu w trakcie symulacji)."""
        return {
            name: {"phase": hd.phase(), "kcal_per_cap": round(hd.last_intake_kcal),
                   "stock_food_mt": round(hd.stock_food_mt, 1)}
            for name, hd in self.hubs.items()
        }

    def report(self) -> pd.DataFrame:
        """Pełna historia dobowa wszystkich hubów."""
        rows = [r for hd in self.hubs.values() for r in hd.history]
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values(["day", "hub"]).reset_index(drop=True)

    def summary(self) -> pd.DataFrame:
        """Podsumowanie na hub: dostawy, spożycie, pokrycie zapotrzebowania [%] i faza z ostatniej doby."""
        rows = []
        for hd in self.hubs.values():
            rows.append({
                "hub": hd.name,
                "population": hd.population,
                "food_need_mt": round(hd.total_need_food, 1),
                "food_delivered_mt": round(hd.total_delivered_food, 1),
                "food_consumed_mt": round(hd.total_consumed_food, 1),
                "unmet_food_mt": round(hd.total_need_food - hd.total_consumed_food, 1),
                "food_coverage_pct": round(100 * hd.total_consumed_food / hd.total_need_food, 1)
                if hd.total_need_food else 0.0,
                "final_phase": hd.phase(),
            })
        return pd.DataFrame(rows)

    def total_coverage_pct(self) -> float:
        need = sum(h.total_need_food for h in self.hubs.values())
        eaten = sum(h.total_consumed_food for h in self.hubs.values())
        return round(100 * eaten / need, 1) if need else 0.0
