"""sim_m2.py – Pętla zdarzeń SimPy, Milestone 2.

ZMIANY względem sim.py (M1):
  1. HUB QUEUES: każdy hub jest zasobem SimPy (Resource) z ograniczoną liczbą doków
     rozładunkowych. Ciężarówka czeka na wolny dok i rozładowuje się przez losowy czas.
  2. DEMAND MODEL: po rozładunku wywołuje DemandModel.deliver(), który aktualizuje
     zapasy. Daily tick (konsumpcja dzienna) chodzi jako osobny proces SimPy.
  3. STOCHASTIC: przed startem trasy losuje ewentualną awarię pojazdu.
  4. CROSSING CLOSURES: sprawdza stochastic.CLOSED_CROSSINGS; jeśli przejście
     jest zamknięte, ciężarówka czeka w stanie QUEUE aż do otwarcia.
  5. EDGE USAGE: śledzi licznik przejazdów dla każdej krawędzi (do mapy zatorów).
  6. CARGO QUANTITY: szacuje masę ładunku [t] z kolumny quantity i unit.

Użycie (z run_m2.py):
    log, edge_usage = sim_m2.run_simulation(trucks, G, router, crossing_nodes,
                       hub_nodes, hub_shares, demand_model=dm, events=all_events,
                       rng=rng, month=month)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import simpy

import config
from fsm import S, TruckFSM
import stochastic

# ---------------------------------------------------------------------------
# Parametry hubów (ZAŁOŻENIA – brak danych o liczbie doków)
# ---------------------------------------------------------------------------
# Liczba równoległych stanowisk rozładunku w hubie.
HUB_UNLOAD_DOCKS = {
    "Hub_Rafah": 4,
    "Hub_Khan_Younis": 3,
    "Hub_Deir_al_Balah": 3,
    "Hub_Gaza_City": 2,
    "Hub_North_Jabalia": 2,
}
DEFAULT_HUB_DOCKS = 2

# Czas rozładunku [min] – Erlang(3) o średniej UNLOAD_MEAN_MIN (ZAŁOŻENIE)
UNLOAD_MEAN_MIN = 30.0
UNLOAD_ERLANG_K = 3


def _estimate_mt(quantity, unit: str) -> float:
    """Szacuje masę ładunku [tony] z wartości liczbowej i jednostki."""
    if pd.isna(quantity):
        return 20.0  # domyślna pojemność ciężarówki
    unit = str(unit).strip().lower()
    q = float(quantity)
    if unit in ("mt", "tonnes", "ton", "tons"):
        return max(0.1, q)
    if unit in ("kg", "kilogram", "kilograms"):
        return max(0.1, q / 1000)
    if unit in ("l", "litre", "liter", "liters", "litres"):
        return max(0.1, q / 1000)  # 1 litr wody ≈ 1 kg
    # Nieznana jednostka: zakładamy tony
    return max(0.1, q)


def parse_days(text):
    """'1,3-5' -> {1, 3, 4, 5}. Puste -> zbiór pusty."""
    days = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            days.update(range(int(a), int(b) + 1))
        else:
            days.add(int(part))
    return days


def _clock(minute):
    m = int(minute)
    return f"dz.{m // 1440 + 1:02d} {m % 1440 // 60:02d}:{m % 60:02d}"


def run_simulation(
    trucks: pd.DataFrame,
    G,
    router,
    crossing_nodes: dict,
    hub_nodes: dict,
    hub_shares: pd.DataFrame,
    demand_model=None,
    events=(),
    damage_model=None,
    month: str | None = None,
    seed: int | None = None,
    rng: np.random.Generator | None = None,
    trace_every: int = 0,
    trace_days: set | None = None,
    trace_lines: list | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Zwraca (truck_log DataFrame, edge_usage dict {(u,v): count}).

    edge_usage służy do mapy zatorów w analytics.py.
    """
    month = month or config.MONTH
    if rng is None:
        rng = np.random.default_rng(config.SEED if seed is None else seed)

    t = trucks.sort_values(["date", "truck_id"]).reset_index(drop=True).copy()
    n = len(t)

    # --- losowania z góry (tak samo jak w M1 dla reprodcyowalności) ---
    day_no = (t["date"] - pd.Timestamp(f"{month}-01")).dt.days.to_numpy()
    lo, hi = config.OPEN_HOURS
    t["arrival_min"] = day_no * 1440 + rng.uniform(lo * 60, hi * 60, n)

    if config.SERVICE_DIST == "erlang":
        t["service_min"] = rng.gamma(config.ERLANG_K, config.SERVICE_MEAN_MIN / config.ERLANG_K, n)
    else:
        t["service_min"] = rng.uniform(*config.CLEARANCE_MIN, n)

    t["hub"] = [
        rng.choice(hub_shares.columns.to_numpy(),
                   p=hub_shares.loc[c].to_numpy() / hub_shares.loc[c].sum())
        for c in t["crossing"]
    ]

    # Losowe czasy rozładunku (Erlang)
    t["unload_min"] = rng.gamma(UNLOAD_ERLANG_K, UNLOAD_MEAN_MIN / UNLOAD_ERLANG_K, n)

    # Masa ładunku [t]
    t["cargo_mt"] = [
        _estimate_mt(row.quantity, row.unit) for row in t.itertuples()
    ]

    # Wyznaczenie zestawu śledzonych ciężarówek
    traced: set = set()
    if trace_every:
        traced |= set(t["truck_id"].iloc[::trace_every])
    if trace_days:
        traced |= set(t["truck_id"][pd.Series(day_no + 1).isin(trace_days).to_numpy()])

    # --- środowisko SimPy ---
    env = simpy.Environment()

    # Zasoby przejść granicznych (jak w M1)
    lanes = {
        c: simpy.Resource(env, capacity=config.LANES.get(c, config.DEFAULT_LANES))
        for c in t["crossing"].unique()
    }

    # Zasoby hubów (nowe w M2: doki rozładunkowe)
    hub_docks = {
        h: simpy.Resource(env, capacity=HUB_UNLOAD_DOCKS.get(h, DEFAULT_HUB_DOCKS))
        for h in hub_nodes
    }

    state = {
        "in_transit": 0,
        "delivered": {h: 0 for h in hub_nodes},
        "stuck": 0,
    }
    edge_usage: dict = {}  # (u, v) -> liczba przejazdów
    log = []

    # --- funkcje pomocnicze ---
    def say(truck_id, text):
        if trace_lines is not None and truck_id in traced:
            trace_lines.append(f"[{_clock(env.now)}] #{truck_id} {text}")

    def say_event(text):
        if trace_lines is not None:
            trace_lines.append(f"[{_clock(env.now)}] *** {text}")

    # --- proces zdarzeń drogowych (zniszczenia, blokady, incydenty) ---
    def event_process():
        for ev in sorted(events, key=lambda e: e.minute):
            yield env.timeout(max(0.0, ev.minute - env.now))
            changed = ev.apply(G, damage_model)
            if changed:
                work = router.update(changed)
                say_event(
                    f"{ev.label} | zmienionych krawędzi {len(changed)}, "
                    f"D* Lite naprawił {work} wierzchołków | "
                    f"w drodze {state['in_transit']}, bez drogi {state['stuck']}"
                )
            else:
                say_event(ev.label)

    # --- dobowy tick modelu popytu ---
    def demand_tick_process():
        if demand_model is None:
            return
        day = 0
        while True:
            yield env.timeout(1440)
            day += 1
            demand_model.daily_tick(day)
            snap = demand_model.snapshot()
            worst_ipc = max(v["ipc"] for v in snap.values())
            say_event(
                f"DOBOWY TICK dzień {day} | "
                + "; ".join(
                    f"{h.replace('Hub_', '')}: IPC={v['ipc']} "
                    f"({v['kcal_per_cap']:.0f} kcal, {v['water_l_per_cap']:.1f} l)"
                    for h, v in snap.items()
                )
            )

    # --- proces ciężarówki ---
    def truck(row):
        yield env.timeout(row.arrival_min)
        fsm = TruckFSM(row.truck_id, env.now)

        # --- ETAP 1: Kolejka i odprawa graniczna ---
        lane = lanes[row.crossing]

        # Czekaj, jeśli przejście jest zamknięte (losowe zamknięcia z stochastic.py)
        while row.crossing in stochastic.CLOSED_CROSSINGS:
            yield env.timeout(5)  # sprawdzaj co 5 minut

        fsm.go(S.QUEUE, env.now)
        say(row.truck_id, f"{row.crossing}: wjazd | cel {row.hub}")

        with lane.request() as req:
            yield req
            fsm.go(S.SERVICE, env.now)
            queue = env.now - row.arrival_min
            say(row.truck_id, f"{row.crossing}: odprawa po {queue:.0f} min w kolejce")
            yield env.timeout(row.service_min)

        # --- ETAP 2: Jazda do hubu ---
        fsm.go(S.DRIVE, env.now)
        node = crossing_nodes[row.crossing]
        goal = hub_nodes[row.hub]
        plan = router.plan(row.hub, node)
        seen = router.version
        state["in_transit"] += 1

        t_drive = env.now
        driven_km, replans, stuck_min, delivered = 0.0, 0, 0.0, True
        limit_min = config.STUCK_GIVE_UP_H * 60
        step, half = 0, None

        # Losuj ewentualną awarię pojazdu PRZED startem trasy
        est_km = router.fields[row.hub].cost(node) / 60 * config.TRUCK_SPEED_KMH \
            if hasattr(router, "fields") else 20.0
        breakdown_delay = stochastic.sample_breakdown(est_km, rng)
        if breakdown_delay > 0:
            say(row.truck_id, f"AWARIA pojazdu! Przerwa {breakdown_delay:.0f} min")
            yield env.timeout(breakdown_delay)

        while node != goal:
            # Zaktualizuj trasę, jeśli zmieniły się warunki drogowe
            if seen != router.version:
                new = router.plan(row.hub, node)
                seen = router.version
                if new != plan:
                    replans += 1
                    half = None
                plan = new

            if plan is None:
                if fsm.state != S.STUCK:
                    state["stuck"] += 1
                    fsm.go(S.STUCK, env.now)
                if stuck_min >= limit_min:
                    delivered = False
                    state["stuck"] -= 1
                    fsm.go(S.GAVE_UP, env.now)
                    say(row.truck_id, f"Rezygnuje po {stuck_min / 60:.0f} h bez drogi")
                    break
                stuck_min += config.STUCK_WAIT_MIN
                yield env.timeout(config.STUCK_WAIT_MIN)
                continue

            if fsm.state == S.STUCK:
                state["stuck"] -= 1
                fsm.go(S.DRIVE, env.now)

            nxt = plan.pop(0)
            dt, dkm = router.edge(node, nxt)
            yield env.timeout(dt)

            # Rejestruj przejazd krawędzi (do mapy zatorów)
            key = (node, nxt)
            edge_usage[key] = edge_usage.get(key, 0) + 1

            node = nxt
            driven_km += dkm
            step += 1
            if half is None:
                half = step + max(1, len(plan) // 2)
            if step == half and plan:
                say(row.truck_id, f"w drodze do {row.hub}: {driven_km:.1f} km przejechane")

        t_end_drive = env.now
        state["in_transit"] -= 1

        # --- ETAP 3: Rozładunek w hubie (nowe w M2) ---
        unload_wait_min = 0.0
        if delivered:
            dock = hub_docks[row.hub]
            t_dock_request = env.now
            with dock.request() as req:
                yield req
                unload_wait_min = env.now - t_dock_request
                if unload_wait_min > 0:
                    say(row.truck_id, f"{row.hub}: czeka {unload_wait_min:.0f} min na dok rozładunkowy")
                yield env.timeout(row.unload_min)

            fsm.go(S.DONE, env.now)
            state["delivered"][row.hub] += 1

            # Przekaż ładunek do modelu popytu
            if demand_model is not None:
                demand_model.deliver(
                    hub=row.hub,
                    minute=env.now,
                    cargo_category=str(row.category) if hasattr(row, "category") else "Food",
                    quantity_mt=row.cargo_mt,
                )

            say(row.truck_id,
                f"{row.hub}: rozładunek zakończony | "
                f"w drodze {state['in_transit']}, "
                f"dowiezione {state['delivered'][row.hub]}"
                + (f", zmian trasy {replans}" if replans else ""))

        log.append({
            "truck_id": row.truck_id,
            "date": row.date,
            "crossing": row.crossing,
            "hub": row.hub,
            "cargo_category": getattr(row, "category", None),
            "cargo_mt": row.cargo_mt,
            "arrival_min": row.arrival_min,
            "queue_min": queue,
            "service_min": row.service_min,
            "travel_min": t_end_drive - t_drive,
            "unload_wait_min": unload_wait_min,
            "unload_min": row.unload_min,
            "route_km": driven_km,
            "breakdown_delay_min": breakdown_delay,
            "replans": replans,
            "stuck_min": stuck_min,
            "delivered": delivered,
            "final_state": fsm.state.value,
            "arrival_min_abs": row.arrival_min,
            "done_min": env.now,
        })

    # --- uruchomienie ---
    env.process(event_process())
    env.process(demand_tick_process())
    for row in t.itertuples():
        env.process(truck(row))
    env.run()

    df = pd.DataFrame(log).sort_values("truck_id").reset_index(drop=True)
    return df, edge_usage
