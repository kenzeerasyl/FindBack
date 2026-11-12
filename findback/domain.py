"""Validated public inputs. Hidden simulator truth must never enter these types."""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, isclose
from typing import Mapping

Cell = tuple[int, int]  # row, column; zero-based


def probability(value: float, name: str) -> None:
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between 0 and 1")


@dataclass(frozen=True)
class Belief:
    """Immutable, normalized distribution over exhaustive, exclusive locations."""

    entries: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        names = [name for name, _ in self.entries]
        if not names or any(not n for n in names) or len(set(names)) != len(names):
            raise ValueError("Belief requires unique, nonempty location names")
        for name, value in self.entries:
            probability(value, name)
        if not isclose(sum(v for _, v in self.entries), 1.0, abs_tol=1e-10, rel_tol=0):
            raise ValueError("Belief probabilities must sum to one")

    @classmethod
    def from_dict(cls, values: Mapping[str, float]) -> Belief:
        return cls(tuple((k, float(v)) for k, v in values.items()))

    def as_dict(self) -> dict[str, float]:
        return dict(self.entries)

    def at(self, location: str) -> float:
        try:
            return self.as_dict()[location]
        except KeyError as exc:
            raise ValueError(f"Unknown location: {location}") from exc


@dataclass(frozen=True)
class Campus:
    rows: tuple[str, ...]
    locations: tuple[tuple[str, Cell], ...]
    start: Cell

    def __post_init__(self) -> None:
        if not self.rows or not self.rows[0] or len({len(r) for r in self.rows}) != 1:
            raise ValueError("Map must be a nonempty rectangle")
        if any(ch not in '.#' for row in self.rows for ch in row):
            raise ValueError("Map accepts only '.' and '#'")
        names = [name for name, _ in self.locations]
        cells = [cell for _, cell in self.locations]
        if not names or any(not n for n in names) or len(set(names)) != len(names):
            raise ValueError("Location names must be unique and nonempty")
        if len(set(cells)) != len(cells):
            raise ValueError("Locations must have distinct cells")
        for cell in [self.start, *cells]:
            if not self.walkable(cell):
                raise ValueError(f"Start/location must be on a walkable cell: {cell}")

    def walkable(self, cell: Cell) -> bool:
        r, c = cell
        return (isinstance(r, int) and isinstance(c, int)
                and 0 <= r < len(self.rows) and 0 <= c < len(self.rows[0])
                and self.rows[r][c] == '.')

    def neighbours(self, cell: Cell) -> tuple[Cell, ...]:
        r, c = cell
        return tuple(p for p in ((r-1,c), (r,c+1), (r+1,c), (r,c-1))
                     if self.walkable(p))

    def cell_for(self, name: str) -> Cell:
        try:
            return dict(self.locations)[name]
        except KeyError as exc:
            raise ValueError(f"Unknown location: {name}") from exc

    def with_blocked(self, cell: Cell, blocked: bool = True) -> Campus:
        r, c = cell
        if not (0 <= r < len(self.rows) and 0 <= c < len(self.rows[0])):
            raise ValueError("Cell outside map")
        if blocked and cell in {self.start, *(pos for _, pos in self.locations)}:
            raise ValueError("Cannot block a start or location cell")
        rows = [list(row) for row in self.rows]
        rows[r][c] = '#' if blocked else '.'
        return replace(self, rows=tuple(''.join(row) for row in rows))


@dataclass(frozen=True)
class ObservationModel:
    """ASK returns yes/no; SEARCH returns found/not_found. Conditional independence
    is assumed for distinct evidence events given a stationary item location.
    SEARCH has no false positives: a found item is physically verified.
    """

    sensitivity: float = 0.8
    false_positive: float = 0.1
    detection: float = 0.85

    def __post_init__(self) -> None:
        for name in ('sensitivity', 'false_positive', 'detection'):
            probability(getattr(self, name), name)

    def likelihood(self, kind: str, outcome: str, target: str, actual: str) -> float:
        if kind == 'ask' and outcome in ('yes', 'no'):
            p = self.sensitivity if actual == target else self.false_positive
            return p if outcome == 'yes' else 1-p
        if kind == 'search' and outcome in ('found', 'not_found'):
            p = self.detection if actual == target else 0.0
            return p if outcome == 'found' else 1-p
        raise ValueError(f"Invalid observation: {kind}/{outcome}")


@dataclass(frozen=True)
class Costs:
    move: int = 1
    search: int = 2
    ask: int = 1
    reward_found: float = 100.0
    time_penalty: float = 1.0
    gamma: float = 0.95

    def __post_init__(self) -> None:
        for name in ('move', 'search', 'ask'):
            v = getattr(self, name)
            if type(v) is not int or v <= 0:
                raise ValueError(f"{name} cost must be a positive integer")
        for name in ('reward_found', 'time_penalty'):
            v = getattr(self, name)
            if not isfinite(v) or v < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        probability(self.gamma, 'gamma')


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    campus: Campus
    prior: Belief
    observations: ObservationModel
    costs: Costs
    budget: int

    def __post_init__(self) -> None:
        if set(self.prior.as_dict()) != {name for name, _ in self.campus.locations}:
            raise ValueError("Prior must cover exactly the search locations")
        if type(self.budget) is not int or self.budget <= 0:
            raise ValueError("Budget must be a positive integer")
