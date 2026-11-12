# Mathematical specification

## Hidden world and public information

One stationary item has location L in a finite exhaustive set of search sites.
The agent sees a belief b(l), its current cell x and remaining integer budget B.
Hidden truth belongs only in a separate simulator. The domain and filtering
modules do not contain an actual-item-location field.

The default prior is hypothetical; its role is a starting assumption rather
than evidence collected at a real campus.

The app can accept a last known location. It multiplies that site's prior
weight by three and normalizes the distribution. This multiplier is a heuristic
for the setup form. The experiments use the original priors in scenarios.json.
Selecting the user's current position changes route origins and durations.

## Observations

ASK(k) returns yes or no. For true location l:

```
P(yes | l, ASK(k)) = sensitivity      if l = k
                  = false_positive  otherwise
P(no | l, ASK(k))  = 1 - P(yes | l, ASK(k))
```

SEARCH(k) returns found or not_found:

```
P(found | l, SEARCH(k)) = detection if l = k else 0
P(not_found | l, SEARCH(k)) = 1 - P(found | l, SEARCH(k))
```

Conditional independence is assumed for genuinely separate events given L.
Re-reading the same message is not a new event. The ledger prevents exact-ID
duplicates; it cannot establish that two different witnesses are independent.

## Bayesian filtering

```
w(l) = b(l) * P(observation | l, action)
Z = sum_l w(l)
b_new(l) = w(l) / Z
```

Z is also the predictive probability of the observation and is used for
Bellman branching. Zero-probability outcomes are omitted by a planner; a manual
request to condition on one raises ImpossibleEvidence. A zero prior cannot
be revived by ordinary Bayes, so priors must be chosen carefully.

The update result preserves prior, likelihoods, unnormalized weights, Z and
posterior for an educational calculation table.

## Routing

Cells use (row, column), origin at top left. Four-neighbour motion; unit edge
cost; walls are impassable. Manhattan distance is admissible and consistent.
UCS is the same search with h = 0. The goal is accepted when popped, not when
first generated. A serial tie-breaker makes traversal reproducible.

Route cost is movement steps. Multiply by Costs.move for time. SEARCH also
requires Costs.search units. A route of zero length is valid; an unreachable
route has cost None, never zero. Expanded counts include the popped goal.

## Belief-state planning

The underlying task is a POMDP. A sufficient public information state is
(x, B, b). The planner uses this belief-state MDP and obtains observations from
the user or the simulator.

Finite-depth Bellman lookahead uses unrounded Bayesian beliefs along each
branch. Depth and budget bound the search, and the planner skips
zero-probability outcomes. The plan is optimal within the stated horizon.

Actions: ASK(k), SEARCH(k). STOP has value 0 and is always available. ASK can
be performed remotely without changing position; SEARCH moves to site k.
Unreachable or unaffordable searches are excluded. Every nonterminal action
costs at least one budget unit, so execution cannot loop forever.

The Bellman equation with d remaining planning actions is:

```
V_0(x,B,b) = 0
Q_d(s,a) = -time_penalty * duration(s,a)
           + sum_o P(o | b,a) * [reward_found * I(o=found)
                                + gamma * V_(d-1)(s_o) * I(o!=found)]
V_d(s) = max(0, max_a Q_d(s,a))
```

Gamma is applied once per decision. The model separately charges duration as a
cost and subtracts it from the time budget.
Terminal found and exhausted-budget states have no continuation value.
Ties use deterministic ordering. The planner exposes action values and outcome
branches for auditing and visualization.

At depth one ASK only incurs cost and has no immediate discovery benefit;
its information value requires looking ahead. The tests verify that a second
step can make ASK the highest-value action in a two-site example.

## Experimental validity

Compare planning with nearest-first and highest-belief-first baselines under
the same generated worlds, priors, observation laws, budgets and reward rules.
Report success fraction and time including failed runs, as well as conditional
time among successes (with denominator). Never average successful times alone
and present them as overall cost. Include variability across seeded trials.
Do not promise the sophisticated policy will outperform every baseline.
