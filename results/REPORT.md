# FindBack experimental results

Actual executed episodes: 1200. Python 3.12.14.
Planning depth: 3; seeds 1000–1099.

All recorded paths, observations, Bayesian updates, budgets and returns were replay-audited against the saved seed and current model.

| Scenario | Policy | Success | Wilson 95% interval | Mean time all runs | Mean return |
|---|---|---:|---|---:|---:|
| baseline | planner | 89.0% | 81.4%–93.7% | 20.36 | 59.07 |
| baseline | nearest | 37.0% | 28.2%–46.8% | 19.74 | 16.37 |
| baseline | highest_belief | 46.0% | 36.6%–55.7% | 24.27 | 21.59 |
| weak_reports | planner | 73.0% | 63.6%–80.7% | 23.55 | 45.69 |
| weak_reports | nearest | 37.0% | 28.2%–46.8% | 19.74 | 16.37 |
| weak_reports | highest_belief | 46.0% | 36.6%–55.7% | 24.27 | 21.59 |
| urgent | planner | 34.0% | 25.5%–43.7% | 7.06 | 24.59 |
| urgent | nearest | 8.0% | 4.1%–15.0% | 6.00 | 2.00 |
| urgent | highest_belief | 19.0% | 12.5%–27.8% | 7.00 | 12.00 |
| isolated_library | planner | 53.0% | 43.3%–62.5% | 13.54 | 33.94 |
| isolated_library | nearest | 37.0% | 28.2%–46.8% | 19.74 | 16.37 |
| isolated_library | highest_belief | 37.0% | 28.2%–46.8% | 21.49 | 15.26 |

## Interpretation and limits

- Results apply to the specified fictional maps and correctly specified observation models. They do not establish real-world effectiveness.
- The objective is discounted discovery reward minus time cost, not success rate alone. Early STOP can save time without finding the item.
- Nearest and highest-belief baselines inspect each site at most once and never ask questions. The planner may ask and re-inspect. This compares complete strategies, not a controlled isolation of Bellman planning alone.
- A limited lookahead can undervalue a useful sequence beyond its horizon. Increasing depth may change the policy and increases computation.
- Weak-report scenarios change report quality, not physical search detection. Baselines that never ASK consequently have identical paired outcomes.
- In the isolated-library scenario, items in Library are genuinely unreachable. The unreachable prior mass is not deleted or renormalized away.
- Success intervals are Wilson intervals across independent seeded episodes. Paired return differences with normal-approximation intervals are in summary.json.
- Time among successful runs is separately recorded with its success count. Comparisons above include both successes and failures.
- Repeated ASK events represent new conditionally independent measurements, not re-reading one message. Correlated or adversarial witnesses are not modeled.
- Future validation: unseen maps, misspecified sensor reliability, additional seeds and baselines with matched access to ASK and re-inspection.

## Reproduce

```powershell
python -m findback.experiments --trials 100 --seed 1000 --depth 3
python -m findback.report
```
