"""Optimal four-neighbour grid search with deterministic tie breaking."""
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count

from .domain import Campus, Cell


@dataclass(frozen=True)
class Route:
    path: tuple[Cell, ...]
    cost: int | None
    expanded: tuple[Cell, ...]

    @property
    def reachable(self) -> bool:
        return self.cost is not None


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0]-b[0]) + abs(a[1]-b[1])


def shortest_path(campus: Campus, start: Cell, goal: Cell, *,
                  use_heuristic: bool = True) -> Route:
    """A* (or UCS with use_heuristic=False). Cost is number of moves.

    expanded includes the goal when it is removed from the frontier, although
    its neighbours are not generated. Unreachable is distinct from zero cost.
    """
    if not campus.walkable(start) or not campus.walkable(goal):
        raise ValueError("Route endpoints must be walkable")
    h = (lambda x: manhattan(x, goal)) if use_heuristic else (lambda x: 0)
    serial = count()
    frontier = [(h(start), 0, next(serial), start)]
    best = {start: 0}
    parent: dict[Cell, Cell] = {}
    expanded: list[Cell] = []
    while frontier:
        _, g, _, node = heappop(frontier)
        if g != best[node]:
            continue
        expanded.append(node)
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(parent[path[-1]])
            return Route(tuple(reversed(path)), g, tuple(expanded))
        for nxt in campus.neighbours(node):
            new_g = g+1
            if new_g < best.get(nxt, float('inf')):
                best[nxt] = new_g
                parent[nxt] = node
                heappush(frontier, (new_g+h(nxt), new_g, next(serial), nxt))
    return Route((), None, tuple(expanded))
