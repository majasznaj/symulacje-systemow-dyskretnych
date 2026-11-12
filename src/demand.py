"""demand.py – Warstwa popytowa i wskaźniki bezpieczeństwa żywnościowego (Milestone 2).

Każdy hub obsługuje pewną populację i ma dzienne zapotrzebowanie na pomoc
(kalorie, woda, leki). Symulacja śledzi nadwyżki i deficyty w czasie oraz
wylicza wskaźnik IPC (Integrated Food Security Phase Classification).

Integracja z sim.py:
  - DemandModel.deliver(hub, minute, qty_mt) wywoływana przy każdej dostawie.
  - DemandModel.daily_tick(day) wywoływana co 1440 min (jeden dzień symulacyjny).
  - DemandModel.snapshot() zwraca bieżące KPI dla każdego hubu.
  - Na koniec symulacji DemandModel.report() zwraca DataFrame z historią dobową.
"""

from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Stałe żywieniowe (FAO/WFP – wartości dla populacji dotkniętej kryzysem)
# ---------------------------------------------------------------------------
KCAL_PER_MT_FOOD = 3_300_000   # kcal w 1 tonie żywności (uśrednione)
KCAL_MIN_SURVIVAL = 1_500      # kcal/osobę/dzień – granica przeżycia (IPC 4/5)
KCAL_ADEQUATE = 2_100          # kcal/osobę/dzień – pełne pokrycie potrzeb (IPC 1)
WATER_MIN_L = 3.0              # litry/osobę/dzień – przeżycie (WHO minimum crisis)
WATER_ADEQUATE_L = 15.0        # litry/osobę/dzień – godne warunki (WHO Sphere)
MT_PER_WATER_TRUCK = 20.0      # tony wody w standardowej cysternie
MT_PER_FOOD_TRUCK = 20.0       # tony żywności w standardowej ciężarówce

# Kategorie cargo -> typ towaru
CARGO_TYPE = {
    "Food": "food",
    "Water & Sanitation": "water",
    "Medical": "medical",
    "Shelter": "other",
    "NFI": "other",        # Non-Food Items
    "Fuel": "other",
    "Other": "other",
}


def ipc_phase(kcal_per_capita: float, water_per_capita: float) -> int:
    """Uproszczona klasyfikacja IPC (1–5) na podstawie kalorii i wody."""
    if kcal_per_capita >= KCAL_ADEQUATE and water_per_capita >= WATER_ADEQUATE_L:
        return 1   # Minimal
    if kcal_per_capita >= 1_900 and water_per_capita >= 7.5:
        return 2   # Stressed
    if kcal_per_capita >= 1_700 and water_per_capita >= 5.0:
        return 3   # Crisis
    if kcal_per_capita >= KCAL_MIN_SURVIVAL and water_per_capita >= WATER_MIN_L:
        return 4   # Emergency
    return 5       # Catastrophe / Famine


@dataclass
class HubDemand:
    """Stan zapotrzebowania i zapasów dla jednego hubu."""
    name: str
    population: int         # liczba ludzi w strefie obsługi

    # zapasy bieżące [tony]
    stock_food_mt: float = 0.0
    stock_water_mt: float = 0.0
    stock_medical_mt: float = 0.0

    # skumulowane dostawy i braki [tony]
    total_delivered_food: float = 0.0
    total_delivered_water: float = 0.0
    total_unmet_food_mt: float = 0.0
    total_unmet_water_mt: float = 0.0

    # historia dobowa (jedna krotka na dzień)
    history: List[dict] = field(default_factory=list)

    @property
    def daily_food_need_mt(self) -> float:
        """Dobowe zapotrzebowanie na żywność [tony]."""
        return self.population * KCAL_ADEQUATE / KCAL_PER_MT_FOOD

    @property
    def daily_water_need_mt(self) -> float:
        """Dobowe zapotrzebowanie na wodę [tony]."""
        return self.population * WATER_ADEQUATE_L / 1000  # litry -> tony

    def kcal_per_capita(self) -> float:
        avail_kcal = self.stock_food_mt * KCAL_PER_MT_FOOD
        return avail_kcal / self.population if self.population > 0 else 0.0

    def water_per_capita_l(self) -> float:
        avail_l = self.stock_water_mt * 1000
        return avail_l / self.population if self.population > 0 else 0.0

    def ipc(self) -> int:
        return ipc_phase(self.kcal_per_capita(), self.water_per_capita_l())

    def consume_daily(self, day: int):
        """Zużywa dobową rację – jeśli zapas jest za mały, nalicza unmet demand."""
        need_f = self.daily_food_need_mt
        need_w = self.daily_water_need_mt

        consumed_f = min(self.stock_food_mt, need_f)
        consumed_w = min(self.stock_water_mt, need_w)
        self.total_unmet_food_mt += need_f - consumed_f
        self.total_unmet_water_mt += need_w - consumed_w
        self.stock_food_mt = max(0.0, self.stock_food_mt - need_f)
        self.stock_water_mt = max(0.0, self.stock_water_mt - need_w)

        self.history.append({
            "day": day,
            "hub": self.name,
            "population": self.population,
            "stock_food_mt": round(self.stock_food_mt, 2),
            "stock_water_mt": round(self.stock_water_mt, 2),
            "kcal_per_capita": round(self.kcal_per_capita(), 0),
            "water_per_capita_l": round(self.water_per_capita_l(), 2),
            "ipc_phase": self.ipc(),
            "unmet_food_mt_cum": round(self.total_unmet_food_mt, 2),
            "unmet_water_mt_cum": round(self.total_unmet_water_mt, 2),
        })


class DemandModel:
    """Zarządza stanem popytowym wszystkich hubów przez całą symulację.

    Użycie w sim.py::
        dm = DemandModel(populations)
        # przy każdej dostawie:
        dm.deliver(hub_name, minute, cargo_category, quantity_mt)
        # co 1440 min (lub przez event SimPy):
        dm.daily_tick(day_number)
        # na koniec:
        df = dm.report()
    """

    # Szacowane populacje obsługiwane przez każdy hub (dane WorldPop / UN OCHA, 2024).
    # Wartości są przybliżone – oznaczone ZAŁOŻENIE, do weryfikacji w raporcie.
    DEFAULT_POPULATIONS = {
        "Hub_Rafah":           600_000,   # ZAŁOŻENIE: Rafah + południe; silny napływ przesiedleńców
        "Hub_Khan_Younis":     400_000,   # ZAŁOŻENIE: Khan Younis i okolice
        "Hub_Deir_al_Balah":   350_000,   # ZAŁOŻENIE: centrum Strefy
        "Hub_Gaza_City":       200_000,   # ZAŁOŻENIE: Gaza City (częściowo oblężone)
        "Hub_North_Jabalia":   150_000,   # ZAŁOŻENIE: północ – Jabalia, Beit Lahiya
    }

    def __init__(self, populations: Dict[str, int] = None):
        pops = populations or self.DEFAULT_POPULATIONS
        self.hubs: Dict[str, HubDemand] = {
            name: HubDemand(name=name, population=pop)
            for name, pop in pops.items()
        }

    def deliver(self, hub: str, minute: float, cargo_category: str, quantity_mt: float):
        """Rejestruje dostawę [tony] do danego hubu."""
        if hub not in self.hubs:
            return
        hd = self.hubs[hub]
        cargo = CARGO_TYPE.get(cargo_category, "other")
        if cargo == "food":
            hd.stock_food_mt += quantity_mt
            hd.total_delivered_food += quantity_mt
        elif cargo == "water":
            hd.stock_water_mt += quantity_mt
            hd.total_delivered_water += quantity_mt
        elif cargo == "medical":
            hd.stock_medical_mt += quantity_mt

    def daily_tick(self, day: int):
        """Wywołaj raz na dobę symulacji (SimPy env.timeout(1440))."""
        for hd in self.hubs.values():
            hd.consume_daily(day)

    def snapshot(self) -> Dict[str, dict]:
        """Bieżący stan KPI wszystkich hubów (do logowania w trakcie symulacji)."""
        return {
            name: {
                "ipc": hd.ipc(),
                "kcal_per_cap": round(hd.kcal_per_capita()),
                "water_l_per_cap": round(hd.water_per_capita_l(), 1),
                "stock_food_mt": round(hd.stock_food_mt, 1),
                "stock_water_mt": round(hd.stock_water_mt, 1),
                "unmet_food_mt_cum": round(hd.total_unmet_food_mt, 1),
            }
            for name, hd in self.hubs.items()
        }

    def report(self) -> pd.DataFrame:
        """Pełna historia dobowa wszystkich hubów – DataFrame do CSV."""
        rows = []
        for hd in self.hubs.values():
            rows.extend(hd.history)
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        return df.sort_values(["day", "hub"]).reset_index(drop=True)

    def summary(self) -> pd.DataFrame:
        """Podsumowanie końcowe na hub: łączne dostawy, skumulowany deficyt, końcowy IPC."""
        rows = []
        for hd in self.hubs.values():
            rows.append({
                "hub": hd.name,
                "population": hd.population,
                "total_delivered_food_mt": round(hd.total_delivered_food, 1),
                "total_delivered_water_mt": round(hd.total_delivered_water, 1),
                "total_unmet_food_mt": round(hd.total_unmet_food_mt, 1),
                "total_unmet_water_mt": round(hd.total_unmet_water_mt, 1),
                "food_coverage_pct": round(
                    100 * hd.total_delivered_food
                    / max(1e-9, hd.total_delivered_food + hd.total_unmet_food_mt), 1),
                "final_ipc_phase": hd.ipc(),
            })
        return pd.DataFrame(rows)
