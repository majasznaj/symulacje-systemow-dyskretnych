"""Maszyna stanów ciężarówki (FSM). Każda ciężarówka jest zawsze w jednym stanie, a przejścia są z góry dozwolone.

    wjazd -> (za_strefą) -> kolejka -> odprawa -> jazda <-> bez_drogi
                                   jazda -> rozładunek -> dowiozła
                                   bez_drogi -> zrezygnowała

Stan 'odprawa' oddaje kontrolę do DES (stanowiska na przejściu, zasób SimPy), 'jazda' do routera D* Lite,
'rozładunek' to miejsce na model tłumu w punkcie dystrybucji (na razie tylko czas z config.UNLOAD_MIN).
Nieprawidłowe przejście zgłasza błąd, więc pomyłka w logice wychodzi od razu, a nie jako dziwny wynik.
"""
from enum import Enum


class S(str, Enum):
    ARRIVAL = "wjazd"
    OUTSIDE = "za_strefą"   # strefa przejścia pełna (K), ciężarówka czeka na drodze przed nią
    QUEUE = "kolejka"
    SERVICE = "odprawa"
    DRIVE = "jazda"
    STUCK = "bez_drogi"
    UNLOAD = "rozładunek"
    DONE = "dowiozła"
    GAVE_UP = "zrezygnowała"


ALLOWED = {
    S.ARRIVAL: {S.QUEUE, S.OUTSIDE},
    S.OUTSIDE: {S.QUEUE},
    S.QUEUE: {S.SERVICE},
    S.SERVICE: {S.DRIVE},
    S.DRIVE: {S.STUCK, S.UNLOAD},
    S.STUCK: {S.DRIVE, S.GAVE_UP},
    S.UNLOAD: {S.DONE},
    S.DONE: set(),
    S.GAVE_UP: set(),
}
FINAL = {S.DONE, S.GAVE_UP}


class TruckFSM:
    def __init__(self, truck_id, now):
        self.truck_id = truck_id
        self.state = S.ARRIVAL
        self.history = [(S.ARRIVAL, now)]   # (stan, moment wejścia)

    def go(self, new, now):
        if new not in ALLOWED[self.state]:
            raise RuntimeError(f"ciężarówka #{self.truck_id}: niedozwolone przejście {self.state.value} -> {new.value}")
        self.state = new
        self.history.append((new, now))

    def minutes_in(self, state, now):
        """Łączny czas spędzony w danym stanie (w tym trwający, do chwili now)."""
        total = 0.0
        for i, (s, t0) in enumerate(self.history):
            if s == state:
                t1 = self.history[i + 1][1] if i + 1 < len(self.history) else now
                total += t1 - t0
        return total
