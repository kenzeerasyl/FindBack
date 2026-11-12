"""Reproducible paired-policy experiments and real result exports."""
import argparse
import csv
import json
import math
import platform
from pathlib import Path
from statistics import mean, stdev

from .decision_model import Planner
from .scenarios import load_scenarios
from .simulator import run_episode


def summarize(episodes):
    if not episodes:
        raise ValueError('Cannot summarize zero episodes')
    n = len(episodes)
    k = sum(e.success for e in episodes)
    p = k/n
    z = 1.96
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    successful = [e.time_spent for e in episodes if e.success]
    return {'episodes':n, 'successes':k, 'success_rate':p,
            'success_ci95_wilson':[max(0,center-half),min(1,center+half)],
            'mean_time_all':mean(e.time_spent for e in episodes),
            'mean_time_success_only':mean(successful) if successful else None,
            'mean_discounted_return':mean(e.discounted_return for e in episodes),
            'mean_searches':mean(e.searches for e in episodes),
            'mean_questions':mean(e.questions for e in episodes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials',type=int,default=100)
    parser.add_argument('--seed',type=int,default=1000)
    parser.add_argument('--depth',type=int,default=3)
    parser.add_argument('--out',type=Path,default=Path('results'))
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('--trials must be positive')
    scenarios = load_scenarios()
    report = {'python':platform.python_version(),'depth':args.depth,
              'first_seed':args.seed,'trials_per_policy':args.trials,
              'scenario_inputs':json.loads((Path(__file__).resolve().parent.parent/
                                           'scenarios.json').read_text()),
              'summaries':{},'paired_return_differences':{}}
    records = []
    for key,s in scenarios.items():
        planner = Planner(s,args.depth)
        groups = {}
        report['summaries'][key] = {}
        report['paired_return_differences'][key] = {}
        for policy in ('planner','nearest','highest_belief'):
            episodes = [run_episode(s,seed,policy,args.depth,planner)
                        for seed in range(args.seed,args.seed+args.trials)]
            groups[policy] = episodes
            summary = summarize(episodes)
            report['summaries'][key][policy] = summary
            for e in episodes:
                records.append({'scenario_id':key,**e.to_dict()})
            print(f'{key:18} {policy:14} success={summary["success_rate"]:.1%} '
                  f'time={summary["mean_time_all"]:.2f} '
                  f'return={summary["mean_discounted_return"]:.2f}',flush=True)
        for baseline in ('nearest','highest_belief'):
            diffs = [a.discounted_return-b.discounted_return
                     for a,b in zip(groups['planner'],groups[baseline])]
            se = stdev(diffs)/math.sqrt(len(diffs)) if len(diffs)>1 else None
            report['paired_return_differences'][key][baseline] = {
                'mean':mean(diffs),'standard_error':se,
                'normal_approx_ci95': [mean(diffs)-1.96*se,mean(diffs)+1.96*se]
                    if se is not None else None}
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (args.out/'episodes.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    fields = ['scenario_id','policy','seed','success','time_spent',
              'discounted_return','searches','questions','stop_reason']
    with (args.out/'episodes.csv').open('w',newline='',encoding='utf-8') as f:
        writer = csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)


if __name__ == '__main__':
    main()
