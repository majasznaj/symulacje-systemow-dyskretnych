"""Krok 6: pętla zdarzeń SimPy. Ciężarówka: wjazd -> kolejka i odprawa -> jazda odcinek po odcinku -> dowiozła.

Droga do hubu: na każdym skrzyżowaniu ciężarówka sprawdza, czy stan dróg się zmienił (zdarzenia),
i jeśli tak, bierze nową trasę z pola D* Lite. Gdy nie ma żadnej drogi, czeka i sprawdza ponownie.
"""
import numpy as np
import pandas as pd
import simpy

import config
from fsm import S, TruckFSM


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


def run_simulation(trucks, G, router, crossing_nodes, hub_nodes, hub_shares, events=(),
                   damage_model=None, month=None, seed=None,
                   trace_every=0, trace_days=None, trace_lines=None):
    """Zwraca tabelę z logiem każdej ciężarówki.

    events: lista events.Event (zmiany dróg w czasie). Linie zdarzeń trafiają do trace_lines zawsze,
    a linie ciężarówek tylko dla wybranych (trace_every=50: co 50., trace_days={1,2}: dni miesiąca).
    """
    month = month or config.MONTH
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    t = trucks.sort_values(["date", "truck_id"]).reset_index(drop=True).copy()
    n = len(t)

    # Wszystkie losowania z góry, żeby porównania scenariuszy używały tych samych liczb.
    day_no = (t["date"] - pd.Timestamp(f"{month}-01")).dt.days.to_numpy()
    lo, hi = config.OPEN_HOURS
    t["arrival_min"] = day_no * 1440 + rng.uniform(lo * 60, hi * 60, n)
    if config.SERVICE_DIST == "erlang":
        t["service_min"] = rng.gamma(config.ERLANG_K, config.SERVICE_MEAN_MIN / config.ERLANG_K, n)
    elif config.SERVICE_DIST == "uniform":
        t["service_min"] = rng.uniform(*config.CLEARANCE_MIN, n)
    else:
        raise ValueError(f"config.SERVICE_DIST musi być 'erlang' albo 'uniform', jest {config.SERVICE_DIST!r}")
    # hub losowany z udziałów w Dispatching, niezależnie od przejścia (ZAŁOŻENIE, patrz README)
    t["hub"] = rng.choice(list(hub_shares.index), size=n, p=hub_shares.to_numpy() / hub_shares.sum())

    traced = set()
    if trace_every:
        traced |= set(t["truck_id"].iloc[::trace_every])
    if trace_days:
        traced |= set(t["truck_id"][pd.Series(day_no + 1).isin(trace_days).to_numpy()])

    env = simpy.Environment()
    lanes = {c: simpy.Resource(env, capacity=config.LANES.get(c, config.DEFAULT_LANES))
             for c in t["crossing"].unique()}
    state = {"in_transit": 0, "delivered": {h: 0 for h in hub_shares.index}, "stuck": 0}
    log = []

    def say(truck_id, text):
        if trace_lines is not None and truck_id in traced:
            trace_lines.append(f"[{_clock(env.now)}] #{truck_id} {text}")

    def say_event(text):
        if trace_lines is not None:
            trace_lines.append(f"[{_clock(env.now)}] *** {text}")

    def event_process():
        for ev in sorted(events, key=lambda e: e.minute):
            yield env.timeout(max(0.0, ev.minute - env.now))
            changed = ev.apply(G, damage_model)
            work = router.update(changed)
            full = router.initial_work
            say_event(f"{ev.label} | zmienionych krawędzi {len(changed)}, D* Lite naprawił {work} wierzchołków "
                      f"(liczenie od zera: {full}) | w drodze {state['in_transit']}, bez drogi {state['stuck']}")

    def truck(row):
        yield env.timeout(row.arrival_min)
        fsm = TruckFSM(row.truck_id, env.now)
        lane = lanes[row.crossing]
        say(row.truck_id, f"{row.crossing}: wjazd | czeka {len(lane.queue)}, "
                          f"stanowiska zajęte {lane.count}/{lane.capacity} | cel {row.hub}")
        fsm.go(S.QUEUE, env.now)
        with lane.request() as req:
            yield req
            fsm.go(S.SERVICE, env.now)
            queue = env.now - row.arrival_min
            say(row.truck_id, f"{row.crossing}: początek odprawy po {queue:.0f} min w kolejce")
            yield env.timeout(row.service_min)

        fsm.go(S.DRIVE, env.now)
        node, goal = crossing_nodes[row.crossing], hub_nodes[row.hub]
        plan = router.plan(row.hub, node)
        seen = router.version
        state["in_transit"] += 1
        if row.truck_id in traced:
            if plan is None:
                say(row.truck_id, f"{row.crossing}: odprawa zakończona po {row.service_min:.0f} min, "
                                  f"brak drogi do {row.hub}")
            else:
                pm = pk = 0.0
                a = node
                for b in plan:
                    dt, dkm = router.edge(a, b)
                    pm += dt; pk += dkm; a = b
                say(row.truck_id, f"{row.crossing}: odprawa zakończona po {row.service_min:.0f} min, jedzie do "
                                  f"{row.hub} | plan {pk:.1f} km, {len(plan)} odcinków, {pm:.0f} min")
        t_drive = env.now
        driven_km, replans, stuck_min, step, half = 0.0, 0, 0.0, 0, None
        delivered = True
        limit_min = config.STUCK_GIVE_UP_H * 60
        while node != goal:
            if seen != router.version:   # zmieniły się drogi: weź trasę z aktualnego pola
                new = router.plan(row.hub, node)
                seen = router.version
                if new != plan:
                    replans += 1
                    if new is None:
                        say(row.truck_id, f"w węźle {node}: brak drogi do {row.hub}, czeka")
                    elif plan is None:
                        say(row.truck_id, f"w węźle {node}: droga do {row.hub} znowu istnieje ({len(new)} odcinków)")
                    else:
                        say(row.truck_id, f"OBJAZD w węźle {node}: nowa trasa, zostało {len(new)} odcinków "
                                          f"(było {len(plan)})")
                    half = None
                plan = new
            if plan is None:
                if fsm.state != S.STUCK:
                    state["stuck"] += 1
                    fsm.go(S.STUCK, env.now)
                if stuck_min >= limit_min:   # droga nie wraca: ciężarówka rezygnuje (inaczej symulacja nigdy by się nie skończyła)
                    delivered = False
                    state["stuck"] -= 1
                    fsm.go(S.GAVE_UP, env.now)
                    say(row.truck_id, f"w węźle {node}: brak drogi do {row.hub} od {stuck_min / 60:.0f} h, rezygnuje "
                                      f"(nie dowiozła)")
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
            node = nxt
            driven_km += dkm
            step += 1
            if half is None:
                half = step + len(plan) // 2
            if step == half and plan:
                say(row.truck_id, f"w drodze do {row.hub}: połowa pozostałej trasy "
                                  f"(przejechane {driven_km:.1f} km, odcinków {step}) | w drodze {state['in_transit']}")
        t_end_drive = env.now
        state["in_transit"] -= 1
        if delivered:
            fsm.go(S.DONE, env.now)
            state["delivered"][row.hub] += 1
            say(row.truck_id, f"{row.hub}: dowiozła | w drodze {state['in_transit']}, "
                              f"dowiezione do tego hubu {state['delivered'][row.hub]}, "
                              f"łącznie od wjazdu {env.now - row.arrival_min:.0f} min"
                              + (f", zmian trasy {replans}, czekała bez drogi {stuck_min:.0f} min" if replans or stuck_min else ""))
        log.append({
            "truck_id": row.truck_id, "date": row.date, "crossing": row.crossing, "hub": row.hub,
            "arrival_min": row.arrival_min, "queue_min": queue, "service_min": row.service_min,
            "travel_min": t_end_drive - t_drive, "route_km": driven_km,
            "replans": replans, "stuck_min": stuck_min, "delivered": delivered,
            "final_state": fsm.state.value,
            "cleared_min": row.arrival_min + queue + row.service_min, "done_min": env.now,
        })

    env.process(event_process())
    for row in t.itertuples():
        env.process(truck(row))
    env.run()
    return pd.DataFrame(log).sort_values("truck_id").reset_index(drop=True)
