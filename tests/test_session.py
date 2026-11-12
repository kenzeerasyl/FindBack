import unittest

from findback.decision_model import Action, STOP
from findback.scenarios import load_scenarios
from findback.session import SearchSession


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_scenarios()['baseline']
        self.manual = SearchSession(self.scenario, 'Headphones', 'manual', 42, 3, 30)

    def test_report_then_inspection_updates_budget_position_and_belief(self):
        session = self.manual
        session.report('Library', 'yes', 'witness-01')
        self.assertAlmostEqual(session.state.belief.at('Library'), .32/.38)
        self.assertEqual(session.state.budget, 30)
        session.apply(Action('search', 'Library'), 'not_found')
        self.assertEqual(session.state.position, self.scenario.campus.cell_for('Library'))
        self.assertEqual(session.state.budget, 10)
        self.assertAlmostEqual(session.state.belief.at('Library'), .048/.108)
        self.assertEqual(session.revision, 2)

    def test_invalid_action_and_duplicate_report_leave_state_unchanged(self):
        session = self.manual
        session.report('Library', 'yes', 'Witness')
        previous = session.state
        with self.assertRaises(ValueError):
            session.report('Library', 'yes', ' witness ')
        with self.assertRaises(ValueError):
            session.apply(Action('search', 'Library'), 'invalid')
        self.assertIs(session.state, previous)
        self.assertEqual(len(session.history), 1)

    def test_corridor_edits_recompute_routes_preserving_public_state(self):
        session = self.manual
        session.toggle_cell(0, 8)
        session.toggle_cell(1, 9)
        self.assertIsNone(session.snapshot()['routes']['Library']['steps'])
        self.assertNotIn('SEARCH Library', [a['label'] for a in session.snapshot()['actions']])
        self.assertEqual(session.state.belief, self.scenario.prior)
        session.toggle_cell(1, 9)
        self.assertIsNotNone(session.snapshot()['routes']['Library']['steps'])
        with self.assertRaises(ValueError):
            session.toggle_cell(*session.state.position)

    def test_seeded_world_finds_item_and_does_not_expose_hidden_location(self):
        session = SearchSession(self.scenario, 'Headphones', 'simulation', 42, 3, 30)
        action = session.planner.decide(session.state).chosen
        self.assertEqual(action, Action('search', 'Cafeteria'))
        with self.assertRaises(ValueError):
            session.report('Library', 'yes', 'witness')
        session.apply(action)
        self.assertEqual(session.status, 'found')
        self.assertEqual(session.state.budget, 23)
        self.assertEqual(session.snapshot()['actions'], [])
        self.assertNotIn('actual_location', session.snapshot())

    def test_stop_ends_session_without_spending_budget(self):
        self.manual.apply(STOP)
        self.assertEqual(self.manual.status, 'stopped')
        self.assertEqual(self.manual.state.budget, 30)
        with self.assertRaises(ValueError):
            self.manual.apply(Action('ask', 'Lab'), 'yes')

    def test_personalized_start_and_last_seen_are_distinct_inputs(self):
        session = SearchSession(self.scenario, 'Keys', 'manual', 42, 3, 25,
                                start_at='Cafeteria', last_seen='Lab', description='Silver keyring')
        self.assertEqual(session.state.position, self.scenario.campus.cell_for('Cafeteria'))
        self.assertAlmostEqual(session.state.belief.at('Lab'), .3 / 1.2)
        self.assertAlmostEqual(session.state.belief.at('Cafeteria'), .25 / 1.2)
        self.assertEqual(session.snapshot()['description'], 'Silver keyring')

    def test_replay_restores_personalized_search_and_clue_note(self):
        settings = dict(start_at='Office', last_seen='Library', description='Blue case')
        original = SearchSession(self.scenario, 'Keys', 'manual', 42, 3, 30, **settings)
        original.report('Library', 'yes', 'witness-01', 'Spotted by the counter')
        original.toggle_cell(0, 8)
        original.apply(Action('search', 'Office'), 'not_found')
        restored = SearchSession(self.scenario, 'Keys', 'manual', 42, 3, 30, **settings)
        restored.replay(original.history)
        self.assertEqual(original.snapshot(), restored.snapshot())

    def test_replay_preserves_simulator_attempt_sequence(self):
        original = SearchSession(self.scenario, 'Keys', 'simulation', 42, 3, 30)
        original.apply(Action('ask', 'Lab'))
        restored = SearchSession(self.scenario, 'Keys', 'simulation', 42, 3, 30)
        restored.replay(original.history)
        original.apply(Action('ask', 'Lab'))
        restored.apply(Action('ask', 'Lab'))
        self.assertEqual(original.snapshot(), restored.snapshot())


if __name__ == '__main__':
    unittest.main()
