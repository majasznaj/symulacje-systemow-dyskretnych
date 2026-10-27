"""Router floty: po jednym polu kosztu D* Lite na hub. Ciężarówka w dowolnym węźle czyta z niego następny krok."""
import math

from dstar_lite import DStarLite

INF = math.inf


def effective_cost(d):
    """Koszt krawędzi = czas przejazdu [min]; zamknięta blokadą = nieskończony."""
    return INF if d.get("blocked", 0) > 0 else d["time_min"]


class FieldRouter:
    def __init__(self, G, hub_nodes, start_hint, cost_fn=effective_cost):
        self.G = G
        self.cost_fn = cost_fn
        self.hub_nodes = hub_nodes
        # pole kosztu dla całej floty liczymy do wyczerpania kolejki, więc heurystyka nic nie daje (h_scale=0);
        # koszt jest w minutach, a heurystyka w metrach, więc nie można jej tu mieszać
        self.fields = {h: DStarLite(G, start_hint, node, cost_fn=cost_fn, h_scale=0.0) for h, node in hub_nodes.items()}
        self.version = 0          # rośnie po każdej zmianie kosztów
        self.initial_work = sum(f.compute_all() for f in self.fields.values())

    def _best(self, u, v):
        """Z równoległych krawędzi u->v ta o najmniejszym koszcie."""
        return min(self.G[u][v].values(), key=self.cost_fn)

    def update(self, changed_edges):
        """changed_edges: zbiór par (u, v), których koszt się zmienił. Zwraca liczbę naprawionych wierzchołków."""
        changes = {}
        for u, v in changed_edges:
            if self.G.has_edge(u, v):
                changes[(u, v)] = min(self.cost_fn(d) for d in self.G[u][v].values())
        work = 0
        for f in self.fields.values():
            f.update_edges(changes)
            work += f.compute_all()
        self.version += 1
        return work

    def plan(self, hub, node):
        """Węzły do przejechania z node do hubu (bez node) albo None, gdy nie ma drogi."""
        p = self.fields[hub].path(node)
        return None if p is None else p[1:]

    def edge(self, u, v):
        """(czas [min], długość [km]) odcinka u->v w obecnym stanie dróg."""
        d = self._best(u, v)
        return d["time_min"], d["length"] / 1000

    def cost_to_go(self, hub, node):
        return self.fields[hub].cost(node)
