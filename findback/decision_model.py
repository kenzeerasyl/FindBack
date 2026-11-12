"""Finite-depth Bellman planning on exact posterior beliefs (belief-state MDP).

The environment is partially observed; no true item location is accepted here.
Depth limits the planning horizon, not the number of actions in an episode.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache

from .astar import shortest_path, Route
from .bayes import Evidence, ImpossibleEvidence, update
from .domain import Belief, Cell, Scenario


@dataclass(frozen=True)
class State:
    position: Cell
    budget: int
    belief: Belief
    found: bool = False

    def __post_init__(self):
        if type(self.budget) is not int or self.budget < 0:
            raise ValueError('Remaining budget must be a nonnegative integer')


@dataclass(frozen=True)
class Action:
    kind: str
    target: str = ''

    def __post_init__(self):
        if self.kind not in ('stop','search','ask'):
            raise ValueError('Unknown action')
        if (self.kind == 'stop') != (self.target == ''):
            raise ValueError('Only STOP has no target')

    @property
    def label(self):
        return self.kind.upper() + (f' {self.target}' if self.target else '')


STOP = Action('stop')


@dataclass(frozen=True)
class Branch:
    observation: str
    probability: float
    reward: float
    next_state: State


@dataclass(frozen=True)
class ActionValue:
    action: Action
    duration: int
    q: float
    branches: tuple[Branch, ...]


@dataclass(frozen=True)
class Decision:
    chosen: Action
    values: tuple[ActionValue, ...]
    depth: int

    @property
    def explanation(self):
        best = next(v for v in self.values if v.action == self.chosen)
        return (f'{self.chosen.label}: highest expected discounted net reward '
                f'{best.q:.3f} within a {self.depth}-action lookahead. '
                'Ties prefer STOP, then the scenario order. '
                'This is a limited-horizon recommendation, not guaranteed success.')


class Planner:
    def __init__(self, scenario: Scenario, depth: int = 3):
        if type(depth) is not int or not 1 <= depth <= 4:
            raise ValueError('Depth must be an integer from 1 to 4')
        self.scenario = scenario
        self.depth = depth
        # Instance-local caches: no stale cross-map entries or retained simulators.
        self.route = lru_cache(maxsize=4096)(self._route)
        self.branches = lru_cache(maxsize=20000)(self._branches)
        self.value = lru_cache(maxsize=30000)(self._value)

    def initial(self):
        s = self.scenario
        return State(s.campus.start, s.budget, s.prior)

    def validate(self, state: State):
        if not self.scenario.campus.walkable(state.position):
            raise ValueError('Current position must be walkable')
        if set(state.belief.as_dict()) != set(self.scenario.prior.as_dict()):
            raise ValueError('Belief locations do not match scenario')

    def _route(self, position: Cell, target: str) -> Route:
        return shortest_path(self.scenario.campus, position,
                             self.scenario.campus.cell_for(target))

    def duration(self, state: State, action: Action) -> int | None:
        costs = self.scenario.costs
        if action.kind == 'stop':
            return 0
        self.scenario.campus.cell_for(action.target)
        if action.kind == 'ask':
            return costs.ask
        route = self.route(state.position, action.target)
        return None if route.cost is None else route.cost*costs.move + costs.search

    def actions(self, state: State) -> tuple[Action, ...]:
        if state.found or state.budget == 0:
            return (STOP,)
        result = [STOP]
        for kind in ('search', 'ask'):
            for target, _ in self.scenario.campus.locations:
                a = Action(kind,target)
                duration = self.duration(state,a)
                if duration is not None and duration <= state.budget:
                    result.append(a)
        return tuple(result)

    def _branches(self, state: State, action: Action) -> tuple[Branch, ...]:
        if action == STOP:
            return ()
        if action not in self.actions(state):
            raise ValueError('Action is unavailable, unaffordable or state is terminal')
        duration = self.duration(state,action)
        position = (self.scenario.campus.cell_for(action.target)
                    if action.kind == 'search' else state.position)
        outcomes = ('yes','no') if action.kind == 'ask' else ('found','not_found')
        result = []
        for outcome in outcomes:
            try:
                calculation = update(state.belief,self.scenario.observations,
                                     Evidence('hypothetical',action.kind,action.target,outcome))
            except ImpossibleEvidence:
                continue
            found = outcome == 'found'
            reward = (-self.scenario.costs.time_penalty*duration
                      + self.scenario.costs.reward_found*found)
            result.append(Branch(outcome,calculation.evidence_probability,reward,
                                 State(position,state.budget-duration,calculation.after,found)))
        return tuple(result)

    def q_value(self, state: State, action: Action, depth: int) -> float:
        if action == STOP:
            return 0.0
        return sum(b.probability*(b.reward + self.scenario.costs.gamma*
                   self.value(b.next_state,depth-1)) for b in self.branches(state,action))

    def _value(self, state: State, depth: int) -> float:
        if depth <= 0 or state.found or state.budget == 0:
            return 0.0
        return max(self.q_value(state,a,depth) for a in self.actions(state))

    def decide(self, state: State) -> Decision:
        self.validate(state)
        values = tuple(ActionValue(a,self.duration(state,a),
                                   self.q_value(state,a,self.depth),self.branches(state,a))
                       for a in self.actions(state))
        best = max(values,key=lambda v:v.q)
        return Decision(best.action,values,self.depth)

    def transition(self, state: State, action: Action, observation: str) -> Branch:
        """Apply a manually supplied observation using the same model as planning."""
        self.validate(state)
        for b in self.branches(state,action):
            if b.observation == observation:
                return b
        raise ValueError('Observation impossible or invalid for this action')
