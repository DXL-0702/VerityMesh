"""Kafka-to-Celery boundary without coupling Java to Celery internals."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts.source_revision import SourceRevisionSubmittedEvent


class SourceRevisionDispatcher:
    """Translate one committed domain event into one JSON task envelope."""

    task_name = "veritymesh.source_revision.process"

    def dispatch(self, payload: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        event = SourceRevisionSubmittedEvent.from_payload(payload)
        return self.task_name, event.to_processing_task()
