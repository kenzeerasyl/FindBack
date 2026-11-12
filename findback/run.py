"""Inspect initial Q values and run one complete simulated search."""
import argparse
import json
from pathlib import Path
from .decision_model import Planner
from .scenarios import load_scenarios
from .simulator import run_episode


def main():
    scenarios = load_scenarios()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario',choices=list(scenarios),default='baseline')
    p.add_argument('--policy',choices=['planner','nearest','highest_belief'],default='planner')
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--depth',type=int,default=3)
    p.add_argument('--export',type=Path)
    args = p.parse_args()
    s = scenarios[args.scenario]
    planner = Planner(s,args.depth)
    decision = planner.decide(planner.initial())
    print(f'Initial Bellman values (planner, depth {args.depth}):')
    for v in sorted(decision.values,key=lambda v:-v.q):
        print(f'{v.action.label:22} duration={v.duration:2} Q={v.q:8.3f}')
    print(decision.explanation)
    episode = run_episode(s,args.seed,args.policy,args.depth,planner)
    print(f'\nExecuting policy: {args.policy}, seed={args.seed}')
    for step in episode.steps:
        print(f'{step.number}. {step.action.upper()} {step.target}: '
              f'{step.observation}; remaining={step.budget_after}')
    print(f'End: {episode.stop_reason}; time={episode.time_spent}; '
          f'discounted return={episode.discounted_return:.3f}')
    if args.export:
        args.export.parent.mkdir(parents=True,exist_ok=True)
        args.export.write_text(json.dumps(episode.to_dict(),indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
