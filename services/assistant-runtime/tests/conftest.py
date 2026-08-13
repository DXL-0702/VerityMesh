import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from veritymesh_assistant_runtime.execution_context import ProjectExecutionContext

NOW = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_EXAMPLE_PATH = (
    REPOSITORY_ROOT / "contracts/internal/v1/examples/project-execution-context.valid.json"
)
CONTEXT_EXAMPLE = cast(
    dict[str, object],
    json.loads(CONTEXT_EXAMPLE_PATH.read_text(encoding="utf-8")),
)


@pytest.fixture
def context_factory() -> Callable[..., ProjectExecutionContext]:
    def build(**overrides: object) -> ProjectExecutionContext:
        values = deepcopy(CONTEXT_EXAMPLE)
        values.update(overrides)
        return ProjectExecutionContext.model_validate(values)

    return build
