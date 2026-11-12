# FindBack oral defense

## Opening statement

> FindBack helps a student decide where to search for a lost item when time is limited and reports can be wrong. Bayesian inference updates the probability of each location. A-star calculates walking routes. Bellman planning compares checking a location, asking a question, and stopping. The app shows the evidence behind each recommendation.

## Three-minute demonstration

| Time | Show | Say |
|---|---|---|
| 0:00–0:35 | Baseline search, Cafeteria route, action scores | “Library starts at forty percent. Checking Cafeteria takes seven time units and has the highest expected value over three actions. A-star finds a five-step walking route, and the inspection costs two more units.” |
| 0:35–1:10 | Add a positive Library report with ID `witness-01` | “A positive Library report multiplies its probability by point eight and the other probabilities by point one. The normalized Library probability becomes eighty-four point two one percent.” |
| 1:10–1:45 | Close `(0, 8)` and `(1, 9)`, select Library on the map | “The item could still be in the Library, but there is no route. The planner removes that inspection from its available actions and now recommends asking about Cafeteria.” |
| 1:45–2:15 | Reset to baseline Simulation, seed 42, take the recommendation | “This reproducible trial finds the item in Cafeteria in seven time units. The simulator generates the outcome. The planner only receives observations.” |
| 2:15–3:00 | Experiments tab | “We used one hundred shared seeds per scenario and policy. In the baseline scenario the planner found eighty-nine items, compared with thirty-seven and forty-six for the reference policies. These results apply to the synthetic setup.” |

The app labels are in Russian. Open the baseline using **Новый поиск → Открыть пример**. The corresponding controls for the demo are **Добавить подсказку**, **Настроить проходы**, and **Как это работает**. The last page shows Q values and experiments. To run seed 42, choose **Симуляция** in the new-search settings and use **Выполнить действие**. The notebook also shows the Bayes table and each outcome's Bellman contribution in English.

## Questions and short answers

**Why use Bayes?**  
“A report can be right or wrong. Bayes combines the prior with the likelihood of the report in each possible location.”

**What is the difference between the likelihood and the posterior?**  
“The likelihood asks how probable a report is if the item is at a location. The posterior asks how probable that location is after we see the report.”

**Why does a missed inspection leave a nonzero probability?**  
“The detection probability is eighty-five percent when the item is there. Missing it is still possible, so we lower the location probability.”

**How does A-star choose a cell?**  
“It orders cells by g plus h. g is the walking cost so far. h is Manhattan distance to the destination.”

**Why is Manhattan distance appropriate?**  
“We can move one cell horizontally or vertically at a time. Manhattan distance counts the minimum number of moves without obstacles, so it cannot overestimate the actual path cost.”

**What is the difference between A-star and UCS?**  
“UCS uses g alone. A-star also uses an estimate of the remaining cost. They find the same optimal cost on our grid. Their exploration order can differ.”

**What does Q measure?**  
“It is the expected discounted reward of taking an action and then following the best plan within the remaining lookahead. We pay a time cost and get a reward when we find the item.”

**How did you calculate the initial Cafeteria Q score?**  
“The probability of finding the item is point two five times point eight five, or point two one two five. If found, reward is ninety-three. If missed, reward is minus seven and the continuation is about thirty-eight point four five. Weight the two outcomes and discount the continuation by point nine five. The score is about forty-three point zero one four.”

**Why ask a question when it takes time?**  
“An answer can change which inspection we do next. If that improvement is worth more than the cost of asking, the planner chooses the question.”

**Is this an MDP or a POMDP?**  
“The original environment is partially observable because the item location is hidden. The planner uses a belief-state MDP. Its state includes our position, remaining time, and probability distribution over locations.”

**Does a lookahead of three end the search after three moves?**  
“Three is the planning horizon in actions. After each action we update our belief and plan again. The search ends when the item is found, time runs out, or we choose to stop.”

**How did you make the comparisons fair?**  
“The policies share the same seeds, hidden locations, action costs, budgets, and observation model. The simple policies inspect each reachable site at most once. The comparison measures complete strategies, including the planner's ability to ask and recheck.”

**What limits your conclusion?**  
“We used hypothetical data and a stationary item. The real campus would need a verified map and calibrated evidence rates. Future tests should include items outside the search area and reports that are correlated.”

## Suggested speaking roles

For a team of four, divide the live explanation into Bayes and observations, A* and the campus map, Bellman actions and beliefs, and interface plus experiments. For a smaller team, combine adjacent roles. Agree on the actual contributions before presenting. Everyone should be able to trace the full example.

## AI use

The project was developed with OpenAI Codex for design, implementation, notebook generation, testing and documentation. The repository includes actual executed outputs, automated checks, and a simulation audit. Team members should state their own contributions accurately and demonstrate that they can explain the model and interpret its results.
