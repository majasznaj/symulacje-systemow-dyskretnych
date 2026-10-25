"""D* Lite (Koenig i Likhachev, 2002) na grafie networkx.

Szukamy wstecz: od celu (hub) do startu. Wartość g(s) to koszt dojazdu z węzła s do celu.
Gdy zmieni się koszt krawędzi (nowe zniszczenie, blokada, otwarcie drogi), nie liczymy wszystkiego
od zera, tylko naprawiamy wartości, których ta zmiana dotyczy.

Dwa tryby użycia:
  * jeden pojazd: compute() wyznacza trasę od startu (z heurystyką, jak w oryginale), move_start()
    przesuwa start w miarę jazdy;
  * flota jadąca do tego samego celu: compute_all() naprawia g we WSZYSTKICH węzłach, a każda
    ciężarówka w dowolnym miejscu czyta z pola g następny krok (next_node). Tak używa tego sim.py.
"""
import heapq
import math

INF = math.inf


class DStarLite:
    def __init__(self, G, start, goal, weight="cost", cost_fn=None):
        """cost_fn(dane_krawędzi) -> koszt; domyślnie dane[weight]. Równoległe krawędzie u->v
        zastępujemy jedną o najmniejszym koszcie."""
        self.G = G
        cf = cost_fn or (lambda d: d.get(weight, d["length"]))
        self.succ = {u: {} for u in G.nodes}
        self.pred = {u: {} for u in G.nodes}
        for u, v, d in G.edges(data=True):
            c = cf(d)
            if v not in self.succ[u] or c < self.succ[u][v]:
                self.succ[u][v] = c
                self.pred[v][u] = c
        self.start = start
        self.last = start
        self.goal = goal
        self.km = 0.0
        self.g = {}
        self.rhs = {goal: 0.0}
        self._heap = []
        self._key = {}
        self._push(goal)
        self.expanded = 0  # licznik przetworzonych wierzchołków (miara pracy algorytmu)

    # --- pomocnicze ---
    def _h(self, a, b):
        na, nb = self.G.nodes[a], self.G.nodes[b]
        # 0,99: rzutowanie UTM zniekształca odległości do ~0,2%, bez marginesu heurystyka bywa nieadmisyjna
        return 0.99 * math.hypot(na["x"] - nb["x"], na["y"] - nb["y"])

    def _g(self, s):
        return self.g.get(s, INF)

    def _rhs(self, s):
        return self.rhs.get(s, INF)

    def _calc_key(self, s):
        m = min(self._g(s), self._rhs(s))
        return (m + self._h(self.start, s) + self.km, m)

    def _push(self, s):
        k = self._calc_key(s)
        self._key[s] = k
        heapq.heappush(self._heap, (k, s))

    def _remove(self, s):
        self._key.pop(s, None)

    def _top_key(self):
        while self._heap and self._key.get(self._heap[0][1]) != self._heap[0][0]:
            heapq.heappop(self._heap)  # przestarzały wpis
        return self._heap[0][0] if self._heap else (INF, INF)

    def _update_vertex(self, u):
        if u != self.goal:
            self.rhs[u] = min((c + self._g(v) for v, c in self.succ[u].items()), default=INF)
        self._remove(u)
        if self._g(u) != self._rhs(u):
            self._push(u)

    def _step(self):
        k_old, u = heapq.heappop(self._heap)
        if self._key.get(u) != k_old:
            return
        self.expanded += 1
        k_new = self._calc_key(u)
        if k_old < k_new:
            self._push(u)
        elif self._g(u) > self._rhs(u):
            self.g[u] = self._rhs(u)
            self._remove(u)
            for p in self.pred[u]:
                self._update_vertex(p)
        else:
            self.g[u] = INF
            self._update_vertex(u)
            for p in self.pred[u]:
                self._update_vertex(p)

    # --- obliczanie ---
    def compute(self):
        """Wystarcza, żeby trasa od bieżącego startu była poprawna (z heurystyką)."""
        while self._top_key() < self._calc_key(self.start) or self._rhs(self.start) != self._g(self.start):
            if not self._heap:
                break
            self._step()

    def compute_all(self):
        """Naprawia g we wszystkich węzłach (do opróżnienia kolejki). Po zmianie kosztów robi tylko
        tyle, ile trzeba. Zwraca liczbę przetworzonych wierzchołków."""
        before = self.expanded
        while self._top_key() != (INF, INF):
            self._step()
        return self.expanded - before

    # --- odczyt ---
    def cost(self, s=None):
        return self._g(self.start if s is None else s)

    def next_node(self, s):
        """Następny węzeł na najtańszej trasie z s do celu (None, gdy nie da się dojechać)."""
        best, bv = None, INF
        for v, c in self.succ[s].items():
            val = c + self._g(v)
            if val < bv:
                best, bv = v, val
        return best

    def path(self, s=None):
        """Węzły trasy od s (domyślnie od startu) do celu albo None, gdy trasy nie ma."""
        s = self.start if s is None else s
        if self._g(s) == INF:
            return None
        out = [s]
        while s != self.goal:
            s = self.next_node(s)
            if s is None:
                return None
            out.append(s)
            if len(out) > len(self.succ) + 1:
                raise RuntimeError("Pętla w trasie, wartości g są niespójne")
        return out

    # --- zmiany w trakcie działania ---
    def move_start(self, new_start):
        """Przesuwa start (pojazd pojechał dalej)."""
        self.km += self._h(self.last, new_start)
        self.last = new_start
        self.start = new_start

    def update_edges(self, changes):
        """changes = {(u, v): nowy_koszt} (INF = droga zamknięta). Potem wywołaj compute() lub compute_all()."""
        for (u, v), c in changes.items():
            self.succ[u][v] = c
            self.pred[v][u] = c
            self._update_vertex(u)
