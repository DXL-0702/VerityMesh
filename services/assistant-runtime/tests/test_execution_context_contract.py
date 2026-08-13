import json
from pathlib import Path
from typing import cast

from veritymesh_assistant_runtime.execution_context import ProjectExecutionContext

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPOSITORY_ROOT / "contracts/internal/v1/project-execution-context.schema.json"
EXAMPLE_PATH = (
    REPOSITORY_ROOT / "contracts/internal/v1/examples/project-execution-context.valid.json"
)


def load_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def test_python_context_model_matches_the_canonical_json_schema() -> None:
    canonical_schema = load_json(SCHEMA_PATH)

    assert canonical_schema.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert (
        canonical_schema.pop("$id")
        == "urn:veritymesh:contracts:internal:project-execution-context:1.0"
    )
    assert canonical_schema == ProjectExecutionContext.model_json_schema(mode="validation")


def test_canonical_example_round_trips_through_the_python_consumer() -> None:
    example = load_json(EXAMPLE_PATH)

    context = ProjectExecutionContext.model_validate(example)

    assert context.model_dump(mode="json") == example
