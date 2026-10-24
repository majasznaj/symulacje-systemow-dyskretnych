"""Krok 6: pętla zdarzeń SimPy. Ciężarówka: wjazd -> kolejka i odprawa -> jazda do hubu -> rozładunek."""
import numpy as np
import pandas as pd
import simpy

import config


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
    """Minuty od początku miesiąca -> 'dz.05 09:41'."""
    m = int(minute)
    return f"dz.{m // 1440 + 1:02d} {m % 1440 // 60:02d}:{m % 60:02d}"


def run_simulation(trucks, routes, hub_shares, month=None, seed=None,
                   trace_every=0, trace_days=None, trace_lines=None):
    """Zwraca tabelę z logiem każdej ciężarówki.

    Log tekstowy: trace_every=50 opisuje co 50. ciężarówkę, trace_days={1,2} wszystkie z tych dni
    miesiąca. Linie trafiają do listy trace_lines (w kolejności czasu symulacji).
    """
    month = month or config.MONTH
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    t = trucks.sort_values(["date", "truck_id"]).reset_index(drop=True).copy()
    n = len(t)

    # Wszystkie losowania z góry, żeby porównania scenariuszy (M2) używały tych samych liczb.
    day_no = (t["date"] - pd.Timestamp(f"{month}-01")).dt.days.to_numpy()
    lo, hi = config.OPEN_HOURS
    t["arrival_min"] = day_no * 1440 + rng.uniform(lo * 60, hi * 60, n)
    t["service_min"] = rng.uniform(*config.CLEARANCE_MIN, n)
    t["hub"] = rng.choice(list(hub_shares.index), size=n, p=hub_shares.to_numpy() / hub_shares.sum())

    # które ciężarówki opisujemy w logu tekstowym
    traced = set()
    if trace_every:
        traced |= set(t["truck_id"].iloc[::trace_every])
    if trace_days:
        traced |= set(t["truck_id"][pd.Series(day_no + 1).isin(trace_days).to_numpy()])

    env = simpy.Environment()
    lanes = {c: simpy.Resource(env, capacity=config.LANES.get(c, config.DEFAULT_LANES))
             for c in t["crossing"].unique()}
    state = {"in_transit": 0, "delivered": {h: 0 for h in hub_shares.index}}
    log = []

    def say(truck_id, text):
        if trace_lines is not None and truck_id in traced:
            trace_lines.append(f"[{_clock(env.now)}] #{truck_id} {text}")

    def truck(row):
        yield env.timeout(row.arrival_min)
        lane = lanes[row.crossing]
        say(row.truck_id, f"{row.crossing}: wjazd | czeka {len(lane.queue)}, "
                          f"stanowiska zajęte {lane.count}/{lane.capacity} | cel {row.hub}")
        with lane.request() as req:
            yield req
            queue = env.now - row.arrival_min
            say(row.truck_id, f"{row.crossing}: początek odprawy po {queue:.0f} min w kolejce")
            yield env.timeout(row.service_min)
        route = routes[(row.crossing, row.hub)]
        state["in_transit"] += 1
        say(row.truck_id, f"{row.crossing}: odprawa zakończona po {row.service_min:.0f} min, "
                          f"jedzie do {row.hub} | {route['km']:.1f} km, {len(route['path']) - 1} odcinków, "
                          f"objazd +{max(route['detour_km'], 0):.1f} km, plan {route['minutes']:.0f} min")
        yield env.timeout(route["minutes"])
        state["in_transit"] -= 1
        state["delivered"][row.hub] += 1
        say(row.truck_id, f"{row.hub}: rozładunek | w drodze {state['in_transit']}, "
                          f"dowiezione do tego hubu {state['delivered'][row.hub]}, "
                          f"łącznie od wjazdu {env.now - row.arrival_min:.0f} min")
        log.append({
            "truck_id": row.truck_id, "date": row.date, "crossing": row.crossing, "hub": row.hub,
            "arrival_min": row.arrival_min, "queue_min": queue, "service_min": row.service_min,
            "travel_min": route["minutes"], "route_km": route["km"], "detour_km": route["detour_km"],
            "cleared_min": row.arrival_min + queue + row.service_min, "done_min": env.now,
        })

    for row in t.itertuples():
        env.process(truck(row))
    env.run()
    return pd.DataFrame(log).sort_values("truck_id").reset_index(drop=True)
