"""Build and execute the portable notebook from the current FindBack source."""
import base64
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
CELLS = []


def markdown(source):
    CELLS.append({'cell_type': 'markdown', 'metadata': {},
                  'source': textwrap.dedent(source).strip().splitlines(keepends=True)})


def code(source):
    CELLS.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None,
                  'outputs': [], 'source': textwrap.dedent(source).strip().splitlines(keepends=True)})


def bundle():
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        files = sorted((ROOT / 'findback').glob('*.py'))
        files.extend(ROOT / name for name in ('scenarios.json', 'results/summary.json'))
        for path in files:
            archive.writestr(path.relative_to(ROOT).as_posix(), path.read_bytes())
    return '\n'.join(textwrap.wrap(base64.b64encode(buffer.getvalue()).decode('ascii'), 100))


def build():
    markdown('''
    # FindBack · Campus Lost Item Assistant

    A student has a limited time budget and imperfect clues about an item left on campus. FindBack ranks possible locations, calculates walking routes, and recommends the next search action.

    **Run in Colab:** upload this `.ipynb` file, then choose **Runtime → Run all**. The notebook contains a snapshot of the project modules and data. It uses Python's standard library and displays tables and a campus map in the notebook.

    | Course topic | Algorithm | Role |
    |---|---|---|
    | Probabilistic reasoning | Bayesian inference | Update location probabilities after a report or inspection |
    | Graph search | A* | Find the shortest reachable walking route |
    | Sequential decisions | Bellman lookahead over belief states | Compare inspections, questions and stopping |

    The campus, observation rates and rewards are synthetic. Time is measured in model units. The model assumes one item stays at one of five sites, and distinct observations are independent given its location.
    ''')
    markdown('''
    ## Setup

    The next cell restores the version of the source used in this demonstration into a temporary directory. Each section imports the same implementation as the browser application.
    ''')
    setup = '''
    import base64
    from dataclasses import replace
    from html import escape
    from io import BytesIO
    import json
    from pathlib import Path
    import sys
    from tempfile import mkdtemp
    from zipfile import ZipFile

    project = Path(_build_dir) if "_build_dir" in globals() else Path(mkdtemp(prefix="findback_notebook_"))
    with ZipFile(BytesIO(base64.b64decode(SOURCE_BUNDLE))) as archive:
        archive.extractall(project)
    sys.path.insert(0, str(project))

    from findback.astar import shortest_path
    from findback.bayes import Evidence, update
    from findback.decision_model import Action, Planner
    from findback.experiments import summarize
    from findback.scenarios import load_scenarios
    from findback.simulator import run_episode

    def show(markup):
        if "_capture_html" in globals():
            _capture_html(markup)
        else:
            from IPython.display import HTML, display
            display(HTML(markup))

    def show_table(headers, rows):
        head = "".join(f"<th style='text-align:left'>{escape(str(h))}</th>" for h in headers)
        body = "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in row) + "</tr>" for row in rows)
        show(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")

    scenarios = load_scenarios(project / "scenarios.json")
    baseline = scenarios["baseline"]
    print("Loaded", len(scenarios), "scenarios and", len(baseline.campus.locations), "campus sites.")
    '''
    code('SOURCE_BUNDLE = """\n' + bundle() + '\n"""\n\n' + textwrap.dedent(setup).strip())
    markdown('''
    ## 1. Bayesian inference

    A witness says the headphones might be in the Library. For every site, compute `weight = prior × likelihood`, then `posterior = weight / sum(weights)`. The model uses `P(yes | Library) = 0.80` and `P(yes | elsewhere) = 0.10`.

    Hand calculation for the Library: `0.40 × 0.80 = 0.32`. The other sites contribute `0.60 × 0.10 = 0.06`. The updated Library probability is `0.32 / 0.38 = 84.21%`.
    ''')
    code('''
    report = Evidence("witness-01", "ask", "Library", "yes")
    calculation = update(baseline.prior, baseline.observations, report)
    likelihoods = dict(calculation.likelihoods)
    weights = dict(calculation.weights)
    posterior = calculation.after
    show_table(["Site", "Prior", "Likelihood", "Weight", "Posterior"], [
        (site, f"{p:.2%}", f"{likelihoods[site]:.2f}", f"{weights[site]:.3f}",
         f"{posterior.at(site):.2%}") for site, p in baseline.prior.entries
    ])
    print(f"Normalization constant: {calculation.evidence_probability:.3f}")
    missed = update(posterior, baseline.observations,
                    Evidence("inspection-01", "search", "Library", "not_found"))
    print(f"Library probability after an unsuccessful inspection: {missed.after.at('Library'):.2%}")
    assert abs(sum(posterior.as_dict().values()) - 1) < 1e-12
    assert 0 < missed.after.at("Library") < posterior.at("Library")
    ''')
    markdown('''
    A physical inspection detects the item 85% of the time when it is at that site. A missed inspection lowers the probability for that site to 44.44%.

    ## 2. A* routing

    Start at the main gate and use the Library as the demonstration target. Each edge costs one walking step. The frontier is ordered by `f = g + h`, where `g` is the distance travelled and `h` is Manhattan distance to the goal. Each move changes Manhattan distance by at most one, so the heuristic is consistent. UCS provides a reference cost using `h = 0`.
    ''')
    code('''
    campus = baseline.campus
    goal = campus.cell_for("Library")
    route = shortest_path(campus, campus.start, goal)
    ucs = shortest_path(campus, campus.start, goal, use_heuristic=False)
    assert route.cost == ucs.cost == 18
    show_table(["Method", "Walking steps", "Cells explored"], [
        ("A*", route.cost, len(route.expanded)), ("UCS", ucs.cost, len(ucs.expanded))
    ])

    def show_map(campus, path=()):
        sites = {cell: name for name, cell in campus.locations}
        path_cells = set(path)
        lines = []
        for row, line in enumerate(campus.rows):
            cells = []
            for col, symbol in enumerate(line):
                cell = row, col
                name = sites.get(cell, "")
                label = "YOU" if cell == campus.start else name[:3].upper()
                color = "#283531" if symbol == "#" else "#e7efeb"
                if cell in path_cells:
                    color = "#91e2af"
                cells.append(f"<td title='{escape(name or str(cell))}' style='width:36px;height:30px;"
                             f"background:{color};color:#172820;text-align:center;font-size:11px'>"
                             f"{escape(label)}</td>")
            lines.append("<tr>" + "".join(cells) + "</tr>")
        show("<table aria-label='Campus grid' style='border-spacing:2px'>" + "".join(lines) + "</table>")

    show_map(campus, route.path)
    print("Green: A* route. Dark: blocked. The Library is at the upper-right corner.")
    ''')
    markdown('''
    ## 3. Bellman planning and the complete workflow

    The hidden location makes the original problem partially observable. The planner uses the public information state `(position, remaining budget, posterior)`. For each action it computes the expected sum of immediate reward and discounted continuation across possible observations. STOP has value 0. The lookahead covers up to three decisions, then the planner recomputes after each observation.

    SEARCH uses walking time from A* plus inspection time. ASK uses one time unit, can change the posterior and leaves the user's position unchanged. An externally supplied report updates the belief without consuming time. Simulated outcomes are generated separately from the planner.
    ''')
    code('''
    planner = Planner(baseline, depth=3)
    initial = planner.initial()
    with_report = replace(initial, belief=posterior)
    before = planner.decide(initial)
    after = planner.decide(with_report)
    print(f"Initially: {before.chosen.label}")
    print(f"After the report: {after.chosen.label}")
    show_table(["Action", "Time units", "Q"], [
        (v.action.label, v.duration, f"{v.q:.3f}")
        for v in sorted(after.values, key=lambda v: -v.q)
    ])
    best = next(v for v in after.values if v.action == after.chosen)
    contributions = []
    for branch in best.branches:
        future = planner.value(branch.next_state, planner.depth - 1)
        weighted = branch.probability * (branch.reward + baseline.costs.gamma * future)
        contributions.append((branch.observation, f"{branch.probability:.2%}",
                              f"{branch.reward:.3f}", f"{future:.3f}", f"{weighted:.3f}"))
    show_table(["Outcome", "Probability", "Reward", "Continuation", "Weighted value"], contributions)
    ''')
    code('''
    # Apply the same belief to a campus whose Library entrances are closed.
    closed = scenarios["isolated_library"]
    closed_planner = Planner(closed, depth=3)
    alternative = closed_planner.decide(with_report)
    assert closed_planner.route(with_report.position, "Library").cost is None
    assert Action("search", "Library") not in closed_planner.actions(with_report)
    print(f"Library probability stays at {with_report.belief.at('Library'):.2%}.")
    print(f"With the Library isolated, the recommendation is {alternative.chosen.label}.")

    episode = run_episode(baseline, seed=42)
    show_table(["Step", "Action", "Observation", "Time left"], [
        (s.number, f"{s.action.upper()} {s.target}", s.observation, s.budget_after)
        for s in episode.steps
    ])
    print(f"Seed 42: {episode.stop_reason}, {episode.time_spent} time units, return {episode.discounted_return:.2f}.")
    assert episode.success and episode.time_spent == 7
    ''')
    markdown('''
    ## 4. Experiments

    The saved study used 100 paired seeds per scenario and policy, 1,200 episodes in total. The policies face the same simulated worlds and comparable observation streams. The planner can ask or inspect again. The reference strategies never ask and inspect each reachable site at most once. The comparison therefore measures complete policies.
    ''')
    code('''
    study = json.loads((project / "results/summary.json").read_text(encoding="utf-8"))
    show_table(["Scenario", "Policy", "Successful", "Mean time", "Mean discounted reward"], [
        (scenario, policy, f"{m['successes']}/{m['episodes']}",
         f"{m['mean_time_all']:.2f}", f"{m['mean_discounted_return']:.2f}")
        for scenario, policies in study["summaries"].items() for policy, m in policies.items()
    ])
    # Small live reproduction using the first 12 paired seeds from the full study.
    seeds = range(study["first_seed"], study["first_seed"] + 12)
    for policy in ("planner", "nearest", "highest_belief"):
        sample = summarize([run_episode(baseline, seed, policy, depth=3, planner=planner) for seed in seeds])
        print(f"Live subset · {policy}: {sample['successes']}/{sample['episodes']} finds, "
              f"mean time {sample['mean_time_all']:.2f}")
    ''')
    markdown('''
    The planner found 89 of 100 items on the baseline campus and 34 of 100 in the urgent scenario. Lower report quality reduced baseline-budget success to 73 of 100. These comparisons depend on the configured observation model, costs, and shared budget. The mean time column includes successful and failed episodes.

    For the full study, run `python -m findback.experiments --trials 100 --seed 1000 --depth 3` from the project folder, followed by `python -m findback.report` to audit the exported traces.

    **Limitations:** the map and probabilities are synthetic, the item never moves, and the model assumes independent observations. The horizon can miss useful actions that pay off more than three decisions later. Real deployments would need calibrated evidence rates, verified maps, and tests with correlated reports and a possible location outside the search area.
    ''')
    markdown('''
    ## Source used by the notebook

    The compact source listings below show the three main calculations. The archive also includes the full modules and tests.
    ''')
    code('''
    from inspect import getsource
    for function in (update, shortest_path, Planner.q_value, Planner._value):
        print(getsource(function).strip(), end="\\n\\n")
    ''')


def execute(build_dir):
    namespace = {'__name__': '__findback_notebook__', '_build_dir': build_dir}
    count = 0
    for cell in CELLS:
        if cell['cell_type'] != 'code':
            continue
        count += 1
        stdout = StringIO()
        outputs = cell['outputs']

        def flush_stdout():
            value = stdout.getvalue()
            if value:
                outputs.append({'output_type': 'stream', 'name': 'stdout', 'text': value.splitlines(keepends=True)})
                stdout.seek(0)
                stdout.truncate(0)

        def capture_html(markup):
            flush_stdout()
            outputs.append({'output_type': 'display_data', 'metadata': {},
                            'data': {'text/html': markup, 'text/plain': 'FindBack visual output'}})

        namespace['_capture_html'] = capture_html
        with redirect_stdout(stdout):
            exec(compile(''.join(cell['source']), f'<notebook cell {count}>', 'exec'), namespace)
        flush_stdout()
        cell['execution_count'] = count
    return count


if __name__ == '__main__':
    build()
    with TemporaryDirectory(dir=ROOT / 'tools') as workspace:
        count = execute(workspace)
    document = {'cells': CELLS, 'metadata': {
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': sys.version.split()[0]},
    }, 'nbformat': 4, 'nbformat_minor': 4}
    output = ROOT / 'FindBack_Demo.ipynb'
    output.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'Executed {count} cells and wrote {output.name}.')
