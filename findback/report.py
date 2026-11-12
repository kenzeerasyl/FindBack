"""Build a human-readable report from actual experiment output; audit traces."""
import argparse
import json
from math import isclose
from pathlib import Path

from .decision_model import Action, Planner
from .scenarios import load_scenarios
from .simulator import World


def audit(records):
    scenarios = load_scenarios()
    planners = {key:Planner(s,1) for key,s in scenarios.items()}
    for record in records:
        key = record['scenario_id']
        p = planners[key]
        state = p.initial()
        world = World(scenarios[key],record['seed'])
        total = 0.0
        for i,step in enumerate(record['steps']):
            a = Action(step['action'],step['target'])
            if step['number'] != i+1 or step['belief_before'] != state.belief.as_dict():
                raise ValueError('Invalid event sequence or prior')
            if world.observe(a) != step['observation']:
                raise ValueError('Observation does not match the seeded hidden world')
            b = p.transition(state,a,step['observation'])
            if b.next_state.belief.as_dict() != step['belief_after']:
                raise ValueError('Posterior mismatch')
            if b.next_state.budget != step['budget_after'] or b.reward != step['reward']:
                raise ValueError('Budget/reward mismatch')
            if p.duration(state,a) != step['duration']:
                raise ValueError('Duration mismatch')
            route = p.route(state.position,a.target).path if a.kind=='search' else ()
            if tuple(tuple(c) for c in step['route']) != route:
                raise ValueError('Route mismatch')
            total += p.scenario.costs.gamma**i*b.reward
            state = b.next_state
        if (state.found != record['success'] or
            p.scenario.budget-state.budget != record['time_spent'] or
            not isclose(total,record['discounted_return'],abs_tol=1e-10)):
            raise ValueError('Episode totals mismatch')
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path('results'))
    args = parser.parse_args()
    data = json.loads((args.results/'summary.json').read_text())
    records = json.loads((args.results/'episodes.json').read_text())
    if data['scenario_inputs'] != json.loads(Path('scenarios.json').read_text()):
        raise ValueError('Scenario configuration changed since experiment run')
    count = audit(records)
    lines = ['# FindBack experimental results','',
             f'Actual executed episodes: {count}. Python {data["python"]}.',
             f'Planning depth: {data["depth"]}; seeds '
             f'{data["first_seed"]}–{data["first_seed"]+data["trials_per_policy"]-1}.','',
             'All recorded paths, observations, Bayesian updates, budgets and returns '
             'were replay-audited against the saved seed and current model.','',
             '| Scenario | Policy | Success | Wilson 95% interval | Mean time all runs | Mean return |',
             '|---|---|---:|---|---:|---:|']
    for scenario,policies in data['summaries'].items():
        for policy,m in policies.items():
            lo,hi = m['success_ci95_wilson']
            lines.append(f'| {scenario} | {policy} | {m["success_rate"]:.1%} | '
                         f'{lo:.1%}–{hi:.1%} | {m["mean_time_all"]:.2f} | '
                         f'{m["mean_discounted_return"]:.2f} |')
    lines += ['', '## Interpretation and limits','',
              '- Results apply to the specified fictional maps and correctly specified '
              'observation models. They do not establish real-world effectiveness.',
              '- The objective is discounted discovery reward minus time cost, not '
              'success rate alone. Early STOP can save time without finding the item.',
              '- Nearest and highest-belief baselines inspect each site at most once and '
              'never ask questions. The planner may ask and re-inspect. This compares '
              'complete strategies, not a controlled isolation of Bellman planning alone.',
              '- A limited lookahead can undervalue a useful sequence beyond its horizon. '
              'Increasing depth may change the policy and increases computation.',
              '- Weak-report scenarios change report quality, not physical search detection. '
              'Baselines that never ASK consequently have identical paired outcomes.',
              '- In the isolated-library scenario, items in Library are genuinely unreachable. '
              'The unreachable prior mass is not deleted or renormalized away.',
              '- Success intervals are Wilson intervals across independent seeded episodes. '
              'Paired return differences with normal-approximation intervals are in summary.json.',
              '- Time among successful runs is separately recorded with its success count. '
              'Comparisons above include both successes and failures.',
              '- Repeated ASK events represent new conditionally independent measurements, '
              'not re-reading one message. Correlated or adversarial witnesses are not modeled.',
              '- Future validation: unseen maps, misspecified sensor reliability, additional '
              'seeds and baselines with matched access to ASK and re-inspection.', '',
              '## Reproduce','', '```powershell',
              'python -m findback.experiments --trials 100 --seed 1000 --depth 3',
              'python -m findback.report', '```','']
    (args.results/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Audited {count} episodes; report saved to {args.results / "REPORT.md"}')


if __name__ == '__main__':
    main()
