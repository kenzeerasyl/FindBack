"""Run with python -m findback.demo. No third-party packages required."""
import argparse
import json

from .astar import shortest_path
from .bayes import BeliefTracker, Evidence
from .scenarios import load_scenarios


def main() -> None:
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=list(scenarios), default='baseline')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    args = parser.parse_args()
    s = scenarios[args.scenario]
    tracker = BeliefTracker(s.prior).apply(
        s.observations, Evidence('demo-report-1', 'ask', 'Library', 'yes'))
    calculation = tracker.history[-1][1]
    routes = {}
    for location, cell in s.campus.locations:
        route = shortest_path(s.campus, s.campus.start, cell)
        routes[location] = {'path': route.path, 'steps': route.cost,
                            'expanded': len(route.expanded)}
    output = {'scenario': s.name, 'prior': s.prior.as_dict(),
              'evidence': 'A yes report about Library',
              'likelihoods': dict(calculation.likelihoods),
              'weights': dict(calculation.weights),
              'evidence_probability': calculation.evidence_probability,
              'posterior': tracker.belief.as_dict(), 'routes': routes}
    if args.json:
        print(json.dumps(output, indent=2))
        return
    print(f'FindBack | {s.name}\nEvidence: yes report about Library')
    print('Location      Prior     Likelihood  Posterior  Route steps')
    for location, prior in s.prior.entries:
        distance = routes[location]['steps']
        print(f'{location:12} {prior:8.4f} {dict(calculation.likelihoods)[location]:11.4f}'
              f' {tracker.belief.at(location):10.4f}  '
              f'{distance if distance is not None else "UNREACHABLE"}')
    print(f'P(evidence) = {calculation.evidence_probability:.4f}')
    print('This demo reports beliefs and routes; it does not yet choose an action.')


if __name__ == '__main__':
    main()
