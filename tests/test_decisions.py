import inspect
import unittest
from dataclasses import replace

from findback.domain import Belief, Campus, Costs, ObservationModel, Scenario
from findback.decision_model import Action, Planner, State, STOP
from findback.experiments import summarize
from findback.scenarios import load_scenarios
from findback.simulator import World, choose, run_episode


def tiny():
    return Scenario('Two ends','Information has value before a long walk',
                    Campus(('...........',),(('A',(0,0)),('B',(0,10))),(0,5)),
                    Belief.from_dict({'A':.5,'B':.5}),
                    ObservationModel(.9,.1,1),Costs(search=1),7)


class DecisionTests(unittest.TestCase):
    def test_one_step_hand_calculation(self):
        p = Planner(tiny(),1)
        s = p.initial()
        self.assertAlmostEqual(p.q_value(s,Action('search','A'),1),44)
        self.assertEqual(p.q_value(s,Action('ask','A'),1),-1)
        self.assertEqual(p.decide(s).chosen,Action('search','A'))

    def test_information_value_needs_lookahead(self):
        p = Planner(tiny(),2)
        d = p.decide(p.initial())
        self.assertEqual(d.chosen.kind,'ask')
        v = next(v for v in d.values if v.action==Action('ask','A'))
        self.assertAlmostEqual(v.q, -1+.95*(90-6))

    def test_uninformative_reports_not_chosen(self):
        s = replace(tiny(),observations=ObservationModel(.5,.5,1))
        p = Planner(s,2)
        self.assertEqual(p.decide(p.initial()).chosen.kind,'search')

    def test_exact_budget_and_success_terminal(self):
        p = Planner(replace(tiny(),budget=6),3)
        branch = p.transition(p.initial(),Action('search','A'),'found')
        self.assertEqual(branch.next_state.budget,0)
        self.assertTrue(branch.next_state.found)
        self.assertEqual(p.actions(branch.next_state),(STOP,))
        self.assertEqual(p.value(branch.next_state,3),0)

    def test_ask_preserves_position_search_moves_and_reduces_budget(self):
        p = Planner(tiny(),2)
        s = p.initial()
        a = p.transition(s,Action('ask','A'),'yes')
        self.assertEqual(a.next_state.position,s.position)
        self.assertEqual(a.next_state.budget,6)
        b = p.transition(s,Action('search','A'),'not_found')
        self.assertEqual(b.next_state.position,(0,0))
        self.assertEqual(b.next_state.budget,1)
        self.assertEqual(b.next_state.belief.at('A'),0)

    def test_no_affordable_search(self):
        p = Planner(replace(tiny(),budget=1),3)
        self.assertEqual(p.decide(p.initial()).chosen,STOP)

    def test_zero_reward_stops(self):
        p = Planner(replace(tiny(),costs=Costs(reward_found=0)),2)
        self.assertEqual(p.decide(p.initial()).chosen,STOP)

    def test_unreachable_excluded(self):
        p = Planner(load_scenarios()['isolated_library'],2)
        self.assertNotIn(Action('search','Library'),p.actions(p.initial()))
        with self.assertRaises(ValueError):
            p.transition(p.initial(),Action('search','Library'),'found')

    def test_branches_and_bellman_consistency(self):
        p = Planner(tiny(),3)
        s = p.initial()
        d = p.decide(s)
        self.assertAlmostEqual(max(v.q for v in d.values),p.value(s,3))
        for v in d.values:
            if v.action==STOP:
                continue
            self.assertAlmostEqual(sum(b.probability for b in v.branches),1)
            self.assertAlmostEqual(v.q,sum(b.probability*(b.reward+
                                    p.scenario.costs.gamma*p.value(b.next_state,2))
                                    for b in v.branches))

    def test_impossible_outcome_omitted(self):
        p = Planner(replace(tiny(),prior=Belief.from_dict({'A':1,'B':0})),2)
        outcomes = p.branches(p.initial(),Action('search','A'))
        self.assertEqual(len(outcomes),1)
        self.assertEqual(outcomes[0].observation,'found')
        with self.assertRaises(ValueError):
            p.transition(p.initial(),Action('search','A'),'not_found')

    def test_invalid_public_states_and_depth(self):
        for depth in (0,5,1.2):
            with self.assertRaises(ValueError):
                Planner(tiny(),depth)
        p = Planner(tiny())
        with self.assertRaises(ValueError):
            p.decide(State((-1,0),7,p.scenario.prior))
        with self.assertRaises(ValueError):
            State((0,0),-1,p.scenario.prior)


class SimulationTests(unittest.TestCase):
    def test_reproducibility(self):
        a = run_episode(tiny(),42,depth=2)
        b = run_episode(tiny(),42,depth=2)
        self.assertEqual(a,b)

    def test_public_policy_contract_has_no_hidden_truth(self):
        self.assertEqual(list(inspect.signature(choose).parameters),
                         ['policy','planner','state','checked'])
        p = Planner(tiny(),2)
        self.assertEqual(choose('planner',p,p.initial(),frozenset()),
                         choose('planner',p,p.initial(),frozenset()))
        self.assertNotIn('_location',vars(p))

    def test_paired_observation_streams_independent_of_other_actions(self):
        a,b = World(tiny(),25),World(tiny(),25)
        target = Action('ask','A')
        a.observe(Action('ask','B'))
        self.assertEqual(a.observe(target),b.observe(target))
        self.assertEqual(a.observe(target),b.observe(target))

    def test_episode_accounting_and_termination(self):
        s = tiny()
        for policy in ('planner','nearest','highest_belief'):
            for seed in range(25):
                with self.subTest(policy=policy,seed=seed):
                    e = run_episode(s,seed,policy,depth=2)
                    self.assertLessEqual(len(e.steps),s.budget)
                    self.assertLessEqual(e.time_spent,s.budget)
                    self.assertEqual(e.time_spent,sum(x.duration for x in e.steps))
                    self.assertAlmostEqual(e.discounted_return,
                        sum(s.costs.gamma**i*x.reward for i,x in enumerate(e.steps)))
                    self.assertEqual(e.success,any(x.observation=='found' for x in e.steps))
                    for x in e.steps:
                        self.assertAlmostEqual(sum(x.belief_after.values()),1)

    def test_observation_frequencies_match_model(self):
        # Fixed truth via a degenerate prior, distinct seeded worlds.
        s = replace(tiny(),prior=Belief.from_dict({'A':1,'B':0}))
        n = 2000
        hits = sum(World(s,i).observe(Action('ask','A'))=='yes' for i in range(n))
        false = sum(World(s,i).observe(Action('ask','B'))=='yes' for i in range(n))
        self.assertAlmostEqual(hits/n,.9,delta=.035)
        self.assertAlmostEqual(false/n,.1,delta=.035)

    def test_summary_zero_success_not_misreported_as_zero_time(self):
        s = replace(tiny(),budget=1)
        episodes = [run_episode(s,i,depth=2) for i in range(5)]
        report = summarize(episodes)
        self.assertEqual(report['success_rate'],0)
        self.assertIsNone(report['mean_time_success_only'])
        lo,hi = report['success_ci95_wilson']
        self.assertLessEqual(lo,1e-15)
        self.assertGreater(hi,0)

    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            run_episode(tiny(),1,'bad',2)


if __name__=='__main__':
    unittest.main()
