import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from veritymesh_batch_worker.contracts import SourceRevisionSubmittedEvent
from veritymesh_batch_worker.dispatcher import SourceRevisionDispatcher

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVENT_EXAMPLE = (
    REPOSITORY_ROOT / "contracts/events/v1/examples/source-revision-submitted.valid.json"
)
TASK_EXAMPLE = REPOSITORY_ROOT / "contracts/tasks/v1/examples/source-revision-processing.valid.json"


def event_payload() -> dict[str, Any]:
    payload = json.loads(EVENT_EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_event_is_strict_and_translates_to_json_task() -> None:
    event = SourceRevisionSubmittedEvent.from_payload(event_payload())
    expected_task = json.loads(TASK_EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(expected_task, dict)

    assert event.source_revision_id == "source-revision-1"
    assert event.to_processing_task() == expected_task


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(extra="forbidden"),
        lambda value: value.update(event_type="Other"),
        lambda value: value.update(content_sha256="A" * 64),
        lambda value: value.update(content_length=True),
        lambda value: value.update(deadline_at="not-a-date"),
        lambda value: value.update(occurred_at="2026-08-13T08:00:00"),
        lambda value: value.update(occurred_at="2026-13-13T08:00:00Z"),
        lambda value: value.update(idempotency_key="short"),
    ],
)
def test_event_rejects_contract_violations(change: Any) -> None:
    payload = event_payload()
    change(payload)

    with pytest.raises(ValueError):
        SourceRevisionSubmittedEvent.from_payload(payload)


def test_dispatcher_has_stable_task_name_and_payload() -> None:
    task_name, task = SourceRevisionDispatcher().dispatch(event_payload())

    assert task_name == "veritymesh.source_revision.process"
    assert task["task_id"] == "task-source-revision-1"
    assert isinstance(task, Mapping)
