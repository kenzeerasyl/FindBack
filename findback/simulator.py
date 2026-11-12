"""Hidden world and auditable episode execution. No external packages."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
from random import Random

from .decision_model import Action, Planner, State, STOP
from .domain import Scenario


class World:
    """Keep this object out of the policy API. It is not a security boundary.

    Outcomes use independent streams keyed by (seed, kind, target, attempt).
    Different policies thus share worlds and corresponding potential observations
    without depending on how many unrelated random draws another policy made.
    """
    def __init__(self, scenario: Scenario, seed: int):
        self._scenario = scenario
        self._seed = seed
        names, weights = zip(*scenario.prior.entries)
        self._location = Random(seed).choices(names,weights=weights,k=1)[0]
        self._attempts: dict[tuple[str,str],int] = {}

    def observe(self, action: Action) -> str:
        if action.kind == 'stop':
            raise ValueError('STOP produces no observation')
        self._scenario.campus.cell_for(action.target)
        key = (action.kind,action.target)
        attempt = self._attempts.get(key,0)
        self._attempts[key] = attempt+1
        payload = f'{self._seed}|{action.kind}|{action.target}|{attempt}'.encode()
        u = (int.from_bytes(sha256(payload).digest()[:8],'big') >> 11) / 2**53
        positive = 'yes' if action.kind == 'ask' else 'found'
        negative = 'no' if action.kind == 'ask' else 'not_found'
        p = self._scenario.observations.likelihood(action.kind,positive,
                                                   action.target,self._location)
        return positive if u < p else negative


@dataclass(frozen=True)
class Step:
    number: int
    action: str
    target: str
    observation: str
    duration: int
    reward: float
    budget_after: int
    belief_before: dict[str,float]
    belief_after: dict[str,float]
    route: tuple[tuple[int,int], ...]


@dataclass(frozen=True)
class Episode:
    scenario: str
    policy: str
    seed: int
    success: bool
    time_spent: int
    discounted_return: float
    searches: int
    questions: int
    stop_reason: str
    steps: tuple[Step, ...]

    def to_dict(self):
        return asdict(self)


def choose(policy: str, planner: Planner, state: State,
           checked: frozenset[str]) -> Action:
    """Baseline policies check each reachable site at most once, never ASK.
    Highest-belief breaks ties by duration; nearest breaks ties by belief.
    Both use updated posteriors and the same action feasibility rules.
    """
    if policy == 'planner':
        return planner.decide(state).chosen
    if policy not in ('nearest','highest_belief'):
        raise ValueError('Unknown policy')
    actions = [a for a in planner.actions(state)
               if a.kind == 'search' and a.target not in checked]
    if not actions:
        return STOP
    if policy == 'nearest':
        return min(actions,key=lambda a:(planner.duration(state,a),-state.belief.at(a.target)))
    return min(actions,key=lambda a:(-state.belief.at(a.target),planner.duration(state,a)))


def run_episode(scenario: Scenario, seed: int, policy: str = 'planner',
                depth: int = 3, planner: Planner | None = None) -> Episode:
    planner = planner or Planner(scenario,depth)
    if planner.scenario != scenario or planner.depth != depth:
        raise ValueError('Provided planner configuration differs from episode')
    world = World(scenario,seed)
    state = planner.initial()
    checked = frozenset()
    steps = []
    total = 0.0
    reason = 'budget_exhausted'
    while state.budget > 0 and not state.found:
        a = choose(policy,planner,state,checked)
        if a == STOP:
            reason = 'policy_stopped'
            break
        observation = world.observe(a)
        b = planner.transition(state,a,observation)
        duration = planner.duration(state,a)
        route = planner.route(state.position,a.target).path if a.kind == 'search' else ()
        total += scenario.costs.gamma**len(steps)*b.reward
        steps.append(Step(len(steps)+1,a.kind,a.target,observation,duration,b.reward,
                          b.next_state.budget,state.belief.as_dict(),
                          b.next_state.belief.as_dict(),route))
        if a.kind == 'search':
            checked |= {a.target}
        state = b.next_state
    if state.found:
        reason = 'found'
    return Episode(scenario.name,policy,seed,state.found,scenario.budget-state.budget,
                   total,sum(s.action=='search' for s in steps),
                   sum(s.action=='ask' for s in steps),reason,tuple(steps))
