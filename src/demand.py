"""demand.py – Warstwa popytowa i wskaźnik bezpieczeństwa żywnościowego (opcjonalna warstwa, flaga --demand).

Każdy hub obsługuje ludność swojego gubernatorstwa (data.hub_population_daily: liczby z raportów IPC, osobna dla każdego dnia,
niezależna od wydań pomocy) i ma dzienne zapotrzebowanie na żywność = ludność x 2100 kcal / kcal w tonie.
Dostawy (tylko kategoria "Food Items") zwiększają zapas w hubie. Co dobę ludność zjada tyle, ile jest w zapasie (do pełnej racji).
Zapas jest wspólny w obrębie grupy IPC (północ, środek, Rafah; config.FOOD_SHARED_WITHIN_IPC_GROUP), ale nie przepływa między grupami.
Pokrycie liczy wyłącznie żywność z pomocy z Excela (bez rynku, własnej produkcji i zapasów domowych).

Wskaźnik fazy 1–5 (kcal_phase) jest UPROSZCZONY: tylko progi kalorii zjedzonych w dobie na osobę. Skala nazw faz jest wzięta z IPC,
ale oficjalne IPC łączy wiele wskaźników (spożycie, strategie przetrwania, odżywienie dzieci, śmiertelność), więc to nie jest klasyfikacja IPC.
Wody nie ma, bo w danych ONZ nie ma kategorii wody (Cargo Category: Food, Non-Food, Mixed, Medical).

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
    kcal_per_capita = round(kcal_per_capita, 3)   # 2099.9999999 (błąd float) ma być pełną rację
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
    population: int            # ludność w bieżącej dobie (zmienia się co dobę z tabeli IPC)

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

    def record_day(self, day: int, need: float, consumed: float, stock_share: float):
        """Zapisuje dobę: potrzeba i zjedzone [t] tego huba oraz jego udział w zapasie grupy."""
        self.stock_food_mt = stock_share
        self.total_consumed_food += consumed
        self.total_need_food += need
        self.last_intake_kcal = consumed * KCAL_PER_MT_FOOD / self.population if self.population else 0.0
        self.history.append({
            "day": day,
            "hub": self.name,
            "population": self.population,
            "food_need_mt": round(need, 2),
            "food_consumed_mt": round(consumed, 2),
            "stock_food_mt": round(stock_share, 2),
            "kcal_per_capita": round(self.last_intake_kcal, 0),
            "kcal_phase": self.phase(),
            "unmet_food_mt_cum": round(self.total_need_food - self.total_consumed_food, 2),
        })


class DemandModel:
    """Zarządza stanem popytowym wszystkich hubów przez całą symulację."""

    def __init__(self, population_daily: pd.DataFrame):
        """population_daily: indeks = numer doby (1..N), kolumny = huby, patrz data.hub_population_daily()."""
        self.population_daily = population_daily
        self.hubs: Dict[str, HubDemand] = {
            name: HubDemand(name=name, population=int(population_daily[name].iloc[0])) for name in population_daily.columns}
        # grupa = hub sam (FOOD_SHARED_WITHIN_IPC_GROUP = False) albo grupa IPC (północ / środek / Rafah). Zapas jest wspólny w grupie.
        self.group_of = {h: (config.IPC_SPLIT[h][0] if config.FOOD_SHARED_WITHIN_IPC_GROUP else h) for h in self.hubs}
        self.group_stock: Dict[str, float] = {g: 0.0 for g in set(self.group_of.values())}

    def deliver(self, hub: str, minute: float, cargo_category: str, quantity_mt: float):
        """Rejestruje dostawę [tony] do danego hubu."""
        hd = self.hubs.get(hub)
        if hd is None:
            return
        kind = CARGO_TYPE.get(cargo_category, "other")
        if kind == "food":
            self.group_stock[self.group_of[hub]] += quantity_mt
            hd.total_delivered_food += quantity_mt
        elif kind == "medical":
            hd.stock_medical_mt += quantity_mt

    def daily_tick(self, day: int):
        """Raz na dobę: ludność z tabeli IPC, potem każda grupa zjada rację z wspólnego zapasu.
        Zjedzone dzieli się na huby grupy proporcjonalnie do potrzeb, więc wszystkie huby w grupie mają to samo kcal na osobę."""
        last = self.population_daily.index.max()
        for hd in self.hubs.values():
            hd.population = int(self.population_daily.loc[min(day, last), hd.name])
        for g in self.group_stock:
            members = [hd for h, hd in self.hubs.items() if self.group_of[h] == g]
            need_g = sum(hd.daily_food_need_mt for hd in members)
            eaten_g = min(self.group_stock[g], need_g)
            self.group_stock[g] -= eaten_g
            pop_g = sum(hd.population for hd in members)
            for hd in members:
                share = hd.daily_food_need_mt / need_g if need_g else 0.0
                hd.record_day(day, hd.daily_food_need_mt, eaten_g * share,
                              self.group_stock[g] * (hd.population / pop_g if pop_g else 0.0))

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
        """Podsumowanie miesiąca na hub: dostawy, spożycie, pokrycie [%], średnie kcal na osobę i faza z całego miesiąca."""
        rows = []
        for hd in self.hubs.values():
            h = pd.DataFrame(hd.history)
            pop_days = h["population"].sum() if len(h) else 0
            kcal_mean = hd.total_consumed_food * KCAL_PER_MT_FOOD / pop_days if pop_days else 0.0
            rows.append({
                "hub": hd.name,
                "group": self.group_of[hd.name],
                "population": round(h["population"].mean()) if len(h) else hd.population,
                "food_need_mt": round(hd.total_need_food, 1),
                "food_delivered_mt": round(hd.total_delivered_food, 1),
                "food_consumed_mt": round(hd.total_consumed_food, 1),
                "unmet_food_mt": round(hd.total_need_food - hd.total_consumed_food, 1),
                "stock_end_mt": round(hd.stock_food_mt, 1),
                "stock_end_days": round(hd.stock_food_mt / hd.daily_food_need_mt, 1) if hd.daily_food_need_mt else 0.0,
                "food_coverage_pct": round(100 * hd.total_consumed_food / hd.total_need_food, 1)
                if hd.total_need_food else 0.0,
                "kcal_per_capita_mean": round(kcal_mean),
                "kcal_phase_month": food_phase(kcal_mean),
                "days_phase_4_5": int((h["kcal_phase"] >= 4).sum()) if len(h) else 0,
            })
        return pd.DataFrame(rows)

    def pooled_coverage_pct(self) -> float:
        """Górne ograniczenie: pokrycie, gdyby cała dostarczona żywność mogła trafić do dowolnego huba (min(dostawy, potrzeby) / potrzeby).
        Różnica względem total_coverage_pct to koszt nierównego rozdziału pomocy między hubami."""
        need = sum(h.total_need_food for h in self.hubs.values())
        delivered = sum(h.total_delivered_food for h in self.hubs.values())
        return round(100 * min(delivered, need) / need, 1) if need else 0.0

    def total_coverage_pct(self) -> float:
        need = sum(h.total_need_food for h in self.hubs.values())
        eaten = sum(h.total_consumed_food for h in self.hubs.values())
        return round(100 * eaten / need, 1) if need else 0.0
