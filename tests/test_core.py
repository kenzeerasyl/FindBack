import unittest
from collections import deque
from dataclasses import replace
from math import nan, inf
from random import Random

from findback.astar import shortest_path, manhattan
from findback.bayes import BeliefTracker, Evidence, ImpossibleEvidence, update
from findback.domain import Belief, Campus, Costs, ObservationModel
from findback.scenarios import load_scenarios


def bfs_distance(campus, start, goal):
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        node, cost = queue.popleft()
        if node == goal:
            return cost
        for nxt in campus.neighbours(node):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, cost+1))
    return None


class DomainTests(unittest.TestCase):
    def test_bad_beliefs(self):
        for entries in ((), (('A', .8),), (('A', nan),), (('A', inf),),
                        (('A', -.1), ('B', 1.1)), (('A', .5), ('A', .5))):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                Belief(entries)

    def test_invalid_sensor_probabilities(self):
        for kwargs in ({'detection': 1.1}, {'false_positive': -.1}, {'sensitivity': nan}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ObservationModel(**kwargs)

    def test_invalid_costs(self):
        for kwargs in ({'move': 0}, {'ask': 1.2}, {'search': True},
                       {'gamma': 1.1}, {'time_penalty': -1}, {'reward_found': inf}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Costs(**kwargs)

    def test_scenarios(self):
        scenarios = load_scenarios()
        self.assertEqual(len(scenarios), 4)
        for s in scenarios.values():
            self.assertEqual(len(s.campus.locations), 5)
            self.assertAlmostEqual(sum(s.prior.as_dict().values()), 1)
        base = scenarios['baseline']
        with self.assertRaises(ValueError):
            replace(base, prior=Belief.from_dict({'Elsewhere': 1}))
        with self.assertRaises(ValueError):
            replace(base, budget=0)

    def test_invalid_maps(self):
        for rows in ((), ('..', '.'), ('x.',), ('#.',)):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                Campus(rows, (('A', (0,0)),), (0,0))

    def test_map_edits_are_immutable(self):
        original = load_scenarios()['baseline'].campus
        changed = original.with_blocked((0,8))
        self.assertTrue(original.walkable((0,8)))
        self.assertFalse(changed.walkable((0,8)))
        self.assertEqual(changed.with_blocked((0,8), False), original)
        for cell in (original.start, original.cell_for('Library'), (-1,0)):
            with self.assertRaises(ValueError):
                original.with_blocked(cell)


class BayesTests(unittest.TestCase):
    def setUp(self):
        self.prior = Belief.from_dict({'Library': .4, 'Cafe': .35, 'Class': .25})
        self.model = ObservationModel()

    def test_hand_calculation(self):
        r = update(self.prior, self.model, Evidence('1', 'ask', 'Library', 'yes'))
        self.assertAlmostEqual(r.evidence_probability, .38)
        self.assertAlmostEqual(r.after.at('Library'), .32/.38)
        self.assertAlmostEqual(r.after.at('Cafe'), .035/.38)
        self.assertAlmostEqual(r.after.at('Class'), .025/.38)

    def test_negative_search_is_not_proof_of_absence(self):
        r = update(self.prior, self.model, Evidence('1', 'search', 'Library', 'not_found'))
        self.assertAlmostEqual(r.after.at('Library'), .06/.66)
        self.assertGreater(r.after.at('Library'), 0)

    def test_found_identifies_location(self):
        r = update(self.prior, self.model, Evidence('1', 'search', 'Library', 'found'))
        self.assertEqual(r.after.at('Library'), 1)
        self.assertEqual(r.after.at('Cafe'), 0)

    def test_uninformative_report_leaves_prior_unchanged(self):
        model = ObservationModel(sensitivity=.5, false_positive=.5)
        for answer in ('yes', 'no'):
            r = update(self.prior, model, Evidence('1','ask','Library', answer))
            self.assertEqual(r.after, self.prior)

    def test_more_diagnostic_report_has_larger_effect(self):
        e = Evidence('1','ask','Library','yes')
        strong = update(self.prior, self.model, e)
        weak = update(self.prior, ObservationModel(.6,.4,.85), e)
        self.assertGreater(strong.after.at('Library'), weak.after.at('Library'))

    def test_outcome_probabilities_partition_one_and_recover_prior(self):
        # Law of total probability: averaging posteriors over all observations
        # recovers the prior, useful for later Bellman outcome branching.
        for kind, outcomes in [('ask', ('yes','no')), ('search', ('found','not_found'))]:
            for target, _ in self.prior.entries:
                results = [update(self.prior, self.model, Evidence(str(i),kind,target,o))
                           for i,o in enumerate(outcomes)]
                self.assertAlmostEqual(sum(r.evidence_probability for r in results), 1)
                for name,p in self.prior.entries:
                    expected = sum(r.evidence_probability*r.after.at(name) for r in results)
                    self.assertAlmostEqual(expected, p)

    def test_duplicate_evidence_rejected_without_changing_old_tracker(self):
        tracker = BeliefTracker(self.prior)
        evidence = Evidence('same-report','ask','Library','yes')
        next_tracker = tracker.apply(self.model, evidence)
        self.assertEqual(tracker.belief, self.prior)
        self.assertEqual(len(tracker.history), 0)
        with self.assertRaises(ValueError):
            next_tracker.apply(self.model, evidence)

    def test_impossible_evidence_is_explicit(self):
        prior = Belief.from_dict({'Library': 0, 'Cafe': 1})
        with self.assertRaises(ImpossibleEvidence):
            update(prior, self.model, Evidence('1','search','Library','found'))

    def test_unknown_location_and_bad_events(self):
        with self.assertRaises(ValueError):
            update(self.prior, self.model, Evidence('1','ask','Missing','yes'))
        for args in [('', 'ask','Library','yes'), ('1','ask','Library','found')]:
            with self.assertRaises(ValueError):
                Evidence(*args)


class PathTests(unittest.TestCase):
    def test_zero_distance(self):
        campus = load_scenarios()['baseline'].campus
        r = shortest_path(campus, campus.start, campus.start)
        self.assertEqual(r.cost, 0)
        self.assertEqual(r.path, (campus.start,))

    def test_unreachable_keeps_nonzero_belief(self):
        s = load_scenarios()['isolated_library']
        r = shortest_path(s.campus, s.campus.start, s.campus.cell_for('Library'))
        self.assertFalse(r.reachable)
        self.assertEqual(r.path, ())
        self.assertIsNone(r.cost)
        self.assertEqual(s.prior.at('Library'), .4)

    def test_bad_endpoint(self):
        campus = load_scenarios()['baseline'].campus
        with self.assertRaises(ValueError):
            shortest_path(campus, (-1,0), campus.start)

    def test_all_pairs_and_heuristic_consistency(self):
        campus = load_scenarios()['baseline'].campus
        points = [campus.start, *(cell for _,cell in campus.locations)]
        for start in points:
            for goal in points:
                with self.subTest(start=start,goal=goal):
                    a = shortest_path(campus,start,goal)
                    u = shortest_path(campus,start,goal,use_heuristic=False)
                    self.assertEqual(a.cost,u.cost)
                    self.assertEqual(a.cost,bfs_distance(campus,start,goal))
                    self.assertLessEqual(manhattan(start,goal),a.cost)
                    for cell in a.path:
                        for nxt in campus.neighbours(cell):
                            self.assertLessEqual(manhattan(cell,goal),1+manhattan(nxt,goal))

    def test_random_maps_against_independent_bfs(self):
        rng = Random(42)
        for trial in range(100):
            rows = tuple(''.join('.' if (r,c) in ((0,0),(5,5)) or rng.random()>.3
                                 else '#' for c in range(6)) for r in range(6))
            campus = Campus(rows,(('Goal',(5,5)),),(0,0))
            route = shortest_path(campus,(0,0),(5,5))
            with self.subTest(trial=trial):
                self.assertEqual(route.cost,bfs_distance(campus,(0,0),(5,5)))
                self.assertEqual(route, shortest_path(campus,(0,0),(5,5)))
                if route.reachable:
                    self.assertEqual(len(route.path)-1,route.cost)
                    self.assertEqual(route.path[0],(0,0))
                    self.assertEqual(route.path[-1],(5,5))
                    for a,b in zip(route.path,route.path[1:]):
                        self.assertIn(b,campus.neighbours(a))


if __name__ == '__main__':
    unittest.main()
