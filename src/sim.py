"""Krok 6: pętla zdarzeń SimPy. Ciężarówka: wjazd -> kolejka i odprawa -> jazda do hubu -> rozładunek."""
import numpy as np
import pandas as pd
import simpy

import config


def run_simulation(trucks, routes, hub_shares, month=None, seed=None):
    month = month or config.MONTH
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    t = trucks.sort_values(["date", "truck_id"]).reset_index(drop=True).copy()
    n = len(t)

    # Wszystkie losowania z góry, żeby porównania scenariuszy (M2) używały tych samych liczb.
    day_min = (t["date"] - pd.Timestamp(f"{month}-01")).dt.days.to_numpy() * 1440
    lo, hi = config.OPEN_HOURS
    t["arrival_min"] = day_min + rng.uniform(lo * 60, hi * 60, n)
    t["service_min"] = rng.uniform(*config.CLEARANCE_MIN, n)
    t["hub"] = rng.choice(list(hub_shares.index), size=n, p=hub_shares.to_numpy() / hub_shares.sum())

    env = simpy.Environment()
    lanes = {c: simpy.Resource(env, capacity=config.LANES.get(c, config.DEFAULT_LANES))
             for c in t["crossing"].unique()}
    log = []

    def truck(row):
        yield env.timeout(row.arrival_min)
        with lanes[row.crossing].request() as req:
            yield req
            queue = env.now - row.arrival_min
            yield env.timeout(row.service_min)
        route = routes[(row.crossing, row.hub)]
        yield env.timeout(route["minutes"])
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
