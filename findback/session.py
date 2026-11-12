"""Application state for one live demonstration."""
from dataclasses import asdict, replace

from .bayes import BeliefTracker, Evidence
from .decision_model import Action, Planner, STOP
from .domain import Belief
from .simulator import World


class SearchSession:
    def __init__(self, scenario, item, mode, seed, depth, budget,
                 start_at='', last_seen='', description=''):
        if mode not in ('manual', 'simulation'):
            raise ValueError('Choose a supported search mode.')
        if type(budget) is not int or not 1 <= budget <= 60:
            raise ValueError('Budget must be an integer from 1 to 60.')
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise ValueError('Seed must be an integer from 0 to 2147483647.')
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 60:
            raise ValueError('Enter an item name between 1 and 60 characters.')
        if not isinstance(description, str) or len(description) > 240:
            raise ValueError('Keep the item description within 240 characters.')
        if not isinstance(start_at, str) or not isinstance(last_seen, str):
            raise ValueError('Choose a campus location.')
        self.item = item.strip()
        self.description = description.strip()
        self.mode = mode
        self.seed = seed
        self.start_at = start_at
        self.last_seen = last_seen
        campus = scenario.campus
        if start_at:
            campus = replace(campus, start=campus.cell_for(start_at))
        prior = scenario.prior
        if last_seen:
            prior.at(last_seen)
            weights = {name: p * (3 if name == last_seen else 1) for name, p in prior.entries}
            total = sum(weights.values())
            prior = Belief.from_dict({name: weight / total for name, weight in weights.items()})
        self.scenario = replace(scenario, budget=budget, campus=campus, prior=prior)
        self.planner = Planner(self.scenario, depth)
        self.original_campus = self.scenario.campus
        self.state = self.planner.initial()
        self._world = World(self.scenario, seed) if mode == 'simulation' else None
        self.tracker = BeliefTracker(self.state.belief)
        self.history = []
        self.closed = set()
        self.stopped = False
        self.revision = 0

    @property
    def status(self):
        if self.state.found:
            return 'found'
        if self.stopped:
            return 'stopped'
        if self.state.budget == 0:
            return 'exhausted'
        return 'active'

    def _record(self, event):
        self.history.append(event)
        self.revision += 1

    def apply(self, action, outcome=None):
        if self.status != 'active':
            raise ValueError('Start a new search to continue.')
        if action not in self.planner.actions(self.state):
            raise ValueError('That action exceeds the budget or the route is blocked.')
        if action == STOP:
            self.stopped = True
            self._record({'type': 'stop', 'budget': self.state.budget})
            return
        event_id = f'action:{self.revision + 1}'
        if self._world is not None:
            outcome = self._world.observe(action)
        branch = self.planner.transition(self.state, action, outcome)
        evidence = Evidence(event_id, action.kind, action.target, outcome)
        tracker = self.tracker.apply(self.scenario.observations, evidence)
        route = (self.planner.route(self.state.position, action.target).path
                 if action.kind == 'search' else ())
        event = {
            'type': action.kind, 'target': action.target, 'outcome': outcome,
            'event_id': event_id, 'duration': self.state.budget - branch.next_state.budget,
            'budget': branch.next_state.budget, 'reward': branch.reward, 'route': route,
            'update': self._explain(tracker.history[-1][1]),
        }
        self.state = branch.next_state
        self.tracker = tracker
        self._record(event)

    def report(self, target, outcome, report_id, note=''):
        if self.mode != 'manual' or self.status != 'active':
            raise ValueError('External reports are available during an active manual search.')
        if not isinstance(report_id, str) or not report_id.strip() or len(report_id.strip()) > 60:
            raise ValueError('Enter a report ID between 1 and 60 characters.')
        if not isinstance(note, str) or len(note) > 240:
            raise ValueError('Keep the clue within 240 characters.')
        event_id = f'report:{report_id.strip().casefold()}'
        evidence = Evidence(event_id, 'ask', target, outcome)
        tracker = self.tracker.apply(self.scenario.observations, evidence)
        self.tracker = tracker
        self.state = replace(self.state, belief=tracker.belief)
        self._record({'type': 'report', 'event_id': event_id, 'target': target, 'note': note.strip(),
                      'outcome': outcome, 'duration': 0, 'budget': self.state.budget,
                      'update': self._explain(tracker.history[-1][1])})

    def toggle_cell(self, row, col):
        if self.status != 'active':
            raise ValueError('Start a new search to edit the map.')
        if type(row) is not int or type(col) is not int:
            raise ValueError('Cell coordinates must be integers.')
        cell = (row, col)
        protected = {self.original_campus.start, self.state.position,
                     *(pos for _, pos in self.original_campus.locations)}
        if cell in protected or not self.original_campus.walkable(cell):
            raise ValueError('Select an open corridor or a corridor you closed in this search.')
        blocked = cell not in self.closed
        campus = self.scenario.campus.with_blocked(cell, blocked)
        self.scenario = replace(self.scenario, campus=campus)
        self.planner = Planner(self.scenario, self.planner.depth)
        if blocked:
            self.closed.add(cell)
        else:
            self.closed.remove(cell)
        self._record({'type': 'map', 'cell': cell, 'blocked': blocked,
                      'budget': self.state.budget})

    def replay(self, events):
        """Rebuild a saved search by applying public events to a fresh session."""
        if not isinstance(events, list) or len(events) > 200:
            raise ValueError('Unsupported saved search history.')
        for event in events:
            kind = event['type']
            if kind in ('stop', 'search', 'ask'):
                self.apply(Action(kind, event.get('target', '')), event.get('outcome'))
                if kind != 'stop' and self.history[-1]['outcome'] != event['outcome']:
                    raise ValueError('Saved simulation outcome does not match its seed.')
            elif kind == 'report':
                self.report(event['target'], event['outcome'], event['event_id'].removeprefix('report:'),
                            event.get('note', ''))
            elif kind == 'map':
                self.toggle_cell(*event['cell'])
            else:
                raise ValueError('Unknown event in saved search.')

    @staticmethod
    def _explain(update):
        return {'prior': update.before.as_dict(), 'likelihood': dict(update.likelihoods),
                'weights': dict(update.weights), 'evidence_probability': update.evidence_probability,
                'posterior': update.after.as_dict()}

    def snapshot(self):
        state, planner = self.state, self.planner
        campus = self.scenario.campus
        routes = {}
        for name, _ in campus.locations:
            route = planner.route(state.position, name)
            routes[name] = {'path': route.path, 'steps': route.cost, 'expanded': route.expanded}
        ranked = []
        chosen = None
        if self.status == 'active':
            decision = planner.decide(state)
            chosen = decision.chosen.label
            for v in sorted(decision.values, key=lambda value: -value.q):
                branches = []
                for b in v.branches:
                    continuation = planner.value(b.next_state, planner.depth - 1)
                    branches.append({'observation': b.observation, 'probability': b.probability,
                                     'reward': b.reward, 'continuation': continuation,
                                     'weighted': b.probability * (b.reward + self.scenario.costs.gamma * continuation)})
                ranked.append({'kind': v.action.kind, 'target': v.action.target,
                               'label': v.action.label, 'duration': v.duration, 'q': v.q,
                               'branches': branches})
        return {'revision': self.revision, 'scenario': self.scenario.name,
                'item': self.item, 'description': self.description, 'mode': self.mode,
                'start_at': self.start_at, 'last_seen': self.last_seen,
                'seed': self.seed if self.mode == 'simulation' else None,
                'status': self.status, 'budget': state.budget, 'initial_budget': self.scenario.budget,
                'position': state.position, 'start': campus.start, 'depth': planner.depth,
                'rows': campus.rows, 'original_rows': self.original_campus.rows,
                'closed': sorted(self.closed), 'locations': dict(campus.locations),
                'belief': state.belief.as_dict(), 'prior': self.scenario.prior.as_dict(),
                'observation_model': asdict(self.scenario.observations), 'costs': asdict(self.scenario.costs),
                'routes': routes, 'chosen': chosen, 'actions': ranked, 'history': self.history}
