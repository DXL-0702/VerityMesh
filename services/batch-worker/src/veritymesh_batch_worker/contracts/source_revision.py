"""Language-neutral SourceRevision event and Celery task boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from re import compile as compile_regex
from typing import Any

_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "event_id",
        "event_type",
        "occurred_at",
        "trace_id",
        "request_id",
        "idempotency_key",
        "project_id",
        "source_object_id",
        "source_revision_id",
        "source_zone_key",
        "content_sha256",
        "content_type",
        "content_length",
        "deadline_at",
    }
)


_RFC3339_TIMESTAMP = compile_regex(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _text(
    payload: Mapping[str, Any],
    key: str,
    *,
    minimum: int = 1,
    maximum: int = 256,
) -> str:
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or len(value) < minimum
        or len(value) > maximum
        or not value.strip()
    ):
        raise ValueError(f"{key} must be a non-empty bounded string")
    return value


def _bounded_hash(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key, maximum=64)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{key} must be lowercase SHA-256")
    return value


def _timestamp(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not _RFC3339_TIMESTAMP.fullmatch(value):
        raise ValueError(f"{key} must be an RFC 3339 timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{key} must be an RFC 3339 timestamp") from error
    return value


@dataclass(frozen=True, slots=True)
class SourceRevisionSubmittedEvent:
    """The only event shape accepted by the first processing dispatcher."""

    schema_version: str
    event_id: str
    occurred_at: str
    trace_id: str
    request_id: str
    idempotency_key: str
    project_id: str
    source_object_id: str
    source_revision_id: str
    source_zone_key: str
    content_sha256: str
    content_type: str
    content_length: int
    deadline_at: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SourceRevisionSubmittedEvent:
        if set(payload) != _EVENT_KEYS:
            raise ValueError("SourceRevisionSubmittedEvent fields do not match v1 contract")
        if (
            payload.get("schema_version") != "1.0"
            or payload.get("event_type") != "SourceRevisionSubmitted"
        ):
            raise ValueError("unsupported SourceRevisionSubmittedEvent version or type")
        content_hash = _bounded_hash(payload, "content_sha256")
        content_length = payload.get("content_length")
        if (
            not isinstance(content_length, int)
            or isinstance(content_length, bool)
            or content_length < 0
        ):
            raise ValueError("content_length must be a non-negative integer")
        return cls(
            schema_version="1.0",
            event_id=_text(payload, "event_id"),
            occurred_at=_timestamp(payload, "occurred_at"),
            trace_id=_text(payload, "trace_id"),
            request_id=_text(payload, "request_id"),
            idempotency_key=_text(payload, "idempotency_key", minimum=16),
            project_id=_text(payload, "project_id"),
            source_object_id=_text(payload, "source_object_id"),
            source_revision_id=_text(payload, "source_revision_id"),
            source_zone_key=_text(payload, "source_zone_key", maximum=1024),
            content_sha256=content_hash,
            content_type=_text(payload, "content_type", maximum=256),
            content_length=content_length,
            deadline_at=_timestamp(payload, "deadline_at"),
        )

    def to_processing_task(self) -> dict[str, Any]:
        """Create a deterministic JSON-safe task envelope; never use pickle."""
        return {
            "task_schema_version": "1.0",
            "task_type": "source_revision.process",
            "task_id": f"task-{self.source_revision_id}",
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "idempotency_key": self.idempotency_key,
            "project_id": self.project_id,
            "source_object_id": self.source_object_id,
            "source_revision_id": self.source_revision_id,
            "source_zone_key": self.source_zone_key,
            "content_sha256": self.content_sha256,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "deadline_at": self.deadline_at,
            "attempt": 1,
            "max_attempts": 3,
            "resource_class": "cpu",
        }
