"""Krok 6: pętla zdarzeń SimPy. Ciężarówka: wjazd -> kolejka i odprawa -> jazda odcinek po odcinku -> (rozładunek) -> dowiozła.

Pojemność K (config.CAPACITY_K): gdy w systemie przejścia (odprawa + kolejka) jest już K ciężarówek, nowa jest zawracana,
wraca po config.REJECT_RETRY_H godzinach i po config.MAX_ATTEMPTS odmowach jest odrzucona na stałe (kolumna rejections).

Droga do hubu: na każdym skrzyżowaniu ciężarówka sprawdza, czy stan dróg się zmienił (zdarzenia),
i jeśli tak, bierze nową trasę z pola D* Lite. Gdy nie ma żadnej drogi, czeka i sprawdza ponownie.

Opcje Milestone 2 (domyślnie wyłączone, wtedy wynik jest taki sam jak w M1):
  unload_docks   {hub: liczba doków}: po dojeździe ciężarówka czeka na dok i rozładowuje się (stan UNLOAD),
  demand_model   demand.DemandModel: dostawy zasilają zapasy hubów, co dobę populacja zjada rację,
  closed_crossings  zbiór nazw zamkniętych przejść (stochastic.generate_crossing_closures): ciężarówka czeka z wjazdem,
  breakdowns     losowa awaria pojazdu przed jazdą (stochastic.sample_breakdown),
  edge_usage     słownik {(u, v): liczba przejazdów}, uzupełniany w trakcie (do mapy zatorów).
Losowania M2 idą z osobnego generatora (seed, 11), więc nie zmieniają losowań M1 (przyjazdy, odprawa, hub).
"""
import numpy as np
import pandas as pd
import simpy

import config
import demand
import stochastic
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
                   trace_every=0, trace_days=None, trace_lines=None,
                   unload_docks=None, demand_model=None, closed_crossings=None, breakdowns=False,
                   edge_usage=None):
    """Zwraca tabelę z logiem każdej ciężarówki.

    events: lista events.Event (zmiany dróg w czasie). Linie zdarzeń trafiają do trace_lines zawsze,
    a linie ciężarówek tylko dla wybranych (trace_every=50: co 50., trace_days={1,2}: dni miesiąca).
    """
    month = month or config.MONTH
    seed = config.SEED if seed is None else seed
    rng = np.random.default_rng(seed)
    rng_m2 = np.random.default_rng([seed, 11])   # osobny strumień dla M2: nie rusza losowań M1
    month_days = pd.Timestamp(f"{month}-01").days_in_month
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
    # hub losowany z rozkładu warunkowego P(hub | crossing) z Dispatching
    t["hub"] = [
        rng.choice(hub_shares.columns.to_numpy(),
                   p=hub_shares.loc[c].to_numpy() / hub_shares.loc[c].sum())
        for c in t["crossing"]
    ]
    # M2: czas rozładunku i masa ładunku (osobny generator, liczone zawsze, używane z unload_docks / demand_model)
    t["unload_min"] = rng_m2.gamma(config.UNLOAD_ERLANG_K, config.UNLOAD_MEAN_MIN / config.UNLOAD_ERLANG_K, n)
    t["cargo_mt"] = [demand.estimate_mt(q, u) for q, u in zip(t["quantity"], t["unit"])] \
        if {"quantity", "unit"} <= set(t.columns) else config.TRUCK_PAYLOAD_MT
    if "category" not in t.columns:
        t["category"] = None

    traced = set()
    if trace_every:
        traced |= set(t["truck_id"].iloc[::trace_every])
    if trace_days:
        traced |= set(t["truck_id"][pd.Series(day_no + 1).isin(trace_days).to_numpy()])

    env = simpy.Environment()
    # Trasa z grafu na starcie miesiąca (zniszczenia początkowe, jeszcze bez fal z tego miesiąca).
    baseline_plan = {(c, h): router.plan(h, crossing_nodes[c]) for c in crossing_nodes for h in hub_nodes}
    lanes = {c: simpy.Resource(env, capacity=config.LANES.get(c, config.DEFAULT_LANES))
             for c in t["crossing"].unique()}
    docks = {h: simpy.Resource(env, capacity=unload_docks.get(h, config.DEFAULT_HUB_DOCKS)) for h in hub_nodes} \
        if unload_docks else None
    state = {"in_transit": 0, "delivered": {h: 0 for h in hub_shares.columns}, "stuck": 0, "remaining": n}
    capacity = {c: config.CAPACITY_K.get(c, config.DEFAULT_CAPACITY_K) for c in lanes} if config.CAPACITY_K is not None else {}
    log = []

    def say(truck_id, text):
        if trace_lines is not None and truck_id in traced:
            trace_lines.append(f"[{_clock(env.now)}] #{truck_id} {text}")

    def say_event(text):
        if trace_lines is not None:
            trace_lines.append(f"[{_clock(env.now)}] *** {text}")

    cause_at_version = {}

    def event_process():
        for ev in sorted(events, key=lambda e: e.minute):
            yield env.timeout(max(0.0, ev.minute - env.now))
            changed = ev.apply(G, damage_model)
            if not ev.roads:   # np. zamknięcie przejścia: drogi bez zmian, router nie liczy od nowa
                say_event(ev.label)
                continue
            work = router.update(changed)
            cause_at_version[router.version] = ev.label
            full = router.initial_work
            say_event(f"{ev.label} | zmienionych krawędzi {len(changed)}, D* Lite naprawił {work} wierzchołków "
                      f"(liczenie od zera: {full}) | w drodze {state['in_transit']}, bez drogi {state['stuck']}")

    def demand_process():
        """Co dobę populacja zjada rację z zapasu hubu, przez wszystkie doby miesiąca (także po ostatniej ciężarówce)."""
        day = 0
        while day < month_days:
            yield env.timeout(1440)
            day += 1
            demand_model.daily_tick(day)
            snap = demand_model.snapshot()
            say_event(f"DOBA {day} | " + "; ".join(
                f"{h.replace('Hub_', '')}: faza {v['phase']} ({v['kcal_per_cap']:.0f} kcal/os., zapas {v['stock_food_mt']:.0f} t)"
                for h, v in snap.items()))

    def truck(row):
        yield env.timeout(row.arrival_min)
        fsm = TruckFSM(row.truck_id, env.now)
        lane = lanes[row.crossing]
        k_max = capacity.get(row.crossing)
        rejections, reject_delay = 0, 0.0
        while True:
            while closed_crossings and row.crossing in closed_crossings:   # przejście zamknięte (stochastic): czeka przed bramą
                yield env.timeout(5)
            if k_max is None or lane.count + len(lane.queue) < k_max:
                break
            rejections += 1   # system pełny (K): zawróć
            fsm.go(S.RETURNED, env.now)
            if rejections >= config.MAX_ATTEMPTS:
                fsm.go(S.REJECTED, env.now)
                say(row.truck_id, f"{row.crossing}: system pełny (K={k_max}), odmowa {rejections}. z {config.MAX_ATTEMPTS}, "
                                  f"odrzucona na stałe")
                log.append({
                    "truck_id": row.truck_id, "date": row.date, "crossing": row.crossing, "hub": row.hub,
                    "arrival_min": row.arrival_min, "queue_min": np.nan, "service_min": np.nan,
                    "travel_min": np.nan, "route_km": np.nan, "replans": 0, "replan_causes": "",
                    "stuck_min": 0.0, "delivered": False, "final_state": fsm.state.value,
                    "cleared_min": np.nan, "done_min": env.now,
                    "category": row.category, "cargo_mt": row.cargo_mt,
                    "unload_wait_min": 0.0, "unload_min": 0.0, "breakdown_delay_min": 0.0,
                    "rejections": rejections,
                })
                state["remaining"] -= 1
                return
            say(row.truck_id, f"{row.crossing}: system pełny (K={k_max}), odmowa {rejections}. z {config.MAX_ATTEMPTS}, "
                              f"wraca za {config.REJECT_RETRY_H:g} h")
            yield env.timeout(config.REJECT_RETRY_H * 60)
            reject_delay += config.REJECT_RETRY_H * 60
            fsm.go(S.ARRIVAL, env.now)
        say(row.truck_id, f"{row.crossing}: wjazd | czeka {len(lane.queue)}, "
                          f"stanowiska zajęte {lane.count}/{lane.capacity} | cel {row.hub}")
        fsm.go(S.QUEUE, env.now)
        with lane.request() as req:
            yield req
            fsm.go(S.SERVICE, env.now)
            queue = env.now - row.arrival_min - reject_delay   # czas w kolejce w udanej próbie (bez dób po odmowach)
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
        replan_causes = []
        breakdown_delay = 0.0
        if breakdowns and plan:
            est_km, a = 0.0, node
            for b in plan:
                est_km += router.edge(a, b)[1]
                a = b
            breakdown_delay = stochastic.sample_breakdown(est_km, rng_m2)
            if breakdown_delay > 0:
                say(row.truck_id, f"AWARIA pojazdu, przerwa {breakdown_delay:.0f} min")
                yield env.timeout(breakdown_delay)
        base = baseline_plan.get((row.crossing, row.hub))
        if plan != base and cause_at_version:
            for cause in (cause_at_version[v] for v in sorted(cause_at_version)):
                if cause not in replan_causes:
                    replan_causes.append(cause)
            why = " | ".join(replan_causes)

            def _km(path, start):
                total, a = 0.0, start
                for b in path or []:
                    _, dkm = router.edge(a, b)
                    total += dkm
                    a = b
                return total

            say(row.truck_id, f"TRASA INNA NIŻ 1. DNIA MIESIĄCA: {_km(plan, node):.1f} km, "
                              f"było {_km(base, node):.1f} km | powód: {why}")
        delivered = True
        limit_min = config.STUCK_GIVE_UP_H * 60
        while node != goal:
            if seen != router.version:   # zmieniły się drogi: weź trasę z aktualnego pola
                causes = [cause_at_version[v] for v in range(seen + 1, router.version + 1) if v in cause_at_version]
                new = router.plan(row.hub, node)
                seen = router.version
                if new != plan:
                    replans += 1
                    for cause in causes:
                        if cause not in replan_causes:
                            replan_causes.append(cause)
                    why = "; ".join(causes) if causes else "zmiana kosztów dróg"
                    if new is None:
                        say(row.truck_id, f"w węźle {node}: brak drogi do {row.hub}, czeka | powód: {why}")
                    elif plan is None:
                        say(row.truck_id, f"w węźle {node}: droga do {row.hub} znowu istnieje "
                                          f"({len(new)} odcinków) | powód: {why}")
                    else:
                        say(row.truck_id, f"OBJAZD w węźle {node}: nowa trasa, zostało {len(new)} odcinków "
                                          f"(było {len(plan)}) | powód: {why}")
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
            if edge_usage is not None:
                edge_usage[(node, nxt)] = edge_usage.get((node, nxt), 0) + 1
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
        unload_wait = 0.0
        if delivered:
            if docks:
                fsm.go(S.UNLOAD, env.now)
                t_req = env.now
                with docks[row.hub].request() as dreq:
                    yield dreq
                    unload_wait = env.now - t_req
                    if unload_wait > 0:
                        say(row.truck_id, f"{row.hub}: czeka {unload_wait:.0f} min na dok rozładunkowy")
                    yield env.timeout(row.unload_min)
            fsm.go(S.DONE, env.now)
            state["delivered"][row.hub] += 1
            if demand_model is not None:
                demand_model.deliver(row.hub, env.now, row.category, row.cargo_mt)
            say(row.truck_id, f"{row.hub}: dowiozła | w drodze {state['in_transit']}, "
                              f"dowiezione do tego hubu {state['delivered'][row.hub]}, "
                              f"łącznie od wjazdu {env.now - row.arrival_min:.0f} min"
                              + (f", zmian trasy {replans}, czekała bez drogi {stuck_min:.0f} min" if replans or stuck_min else ""))
        log.append({
            "truck_id": row.truck_id, "date": row.date, "crossing": row.crossing, "hub": row.hub,
            "arrival_min": row.arrival_min, "queue_min": queue, "service_min": row.service_min,
            "travel_min": t_end_drive - t_drive, "route_km": driven_km,
            "replans": replans, "replan_causes": " | ".join(replan_causes),
            "stuck_min": stuck_min, "delivered": delivered,
            "final_state": fsm.state.value,
            "cleared_min": row.arrival_min + queue + row.service_min, "done_min": env.now,
            "category": row.category, "cargo_mt": row.cargo_mt,
            "unload_wait_min": unload_wait, "unload_min": row.unload_min if docks else 0.0,
            "breakdown_delay_min": breakdown_delay, "rejections": rejections,
        })
        state["remaining"] -= 1

    env.process(event_process())
    if demand_model is not None:
        env.process(demand_process())
    for row in t.itertuples():
        env.process(truck(row))
    env.run()
    return pd.DataFrame(log).sort_values("truck_id").reset_index(drop=True)
