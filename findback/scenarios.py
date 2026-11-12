"""Load portable JSON inputs, independent of the process working directory."""
import json
from pathlib import Path

from .domain import Belief, Campus, Costs, ObservationModel, Scenario

DEFAULT_SCENARIOS = Path(__file__).resolve().parent.parent / 'scenarios.json'


def load_scenarios(path: str | Path = DEFAULT_SCENARIOS) -> dict[str, Scenario]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data['schema_version'] != 1:
        raise ValueError("Unsupported scenario schema version")
    result = {}
    for item in data['scenarios']:
        key = item['id']
        if key in result:
            raise ValueError(f"Duplicate scenario ID: {key}")
        spec = data['maps'][item['map']]
        campus = Campus(tuple(spec['rows']),
                        tuple((k, tuple(v)) for k, v in spec['locations'].items()),
                        tuple(spec['start']))
        for cell in item.get('closed_cells', []):
            campus = campus.with_blocked(tuple(cell))
        result[key] = Scenario(item['name'], item['description'], campus,
                               Belief.from_dict(item['prior']),
                               ObservationModel(**item['observations']),
                               Costs(**item['costs']), item['budget'])
    if not result:
        raise ValueError("At least one scenario is required")
    return result
