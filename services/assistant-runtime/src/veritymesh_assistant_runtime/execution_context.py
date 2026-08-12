"""Immutable execution context and request deadline boundaries."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=256,
        pattern=r"^\S+$",
    ),
]
LocaleTag = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
    ),
]
AccessContextHash = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]


class AccessSegment(StrEnum):
    """Access segment resolved by the Java authorization authority."""

    PUBLIC = "PUBLIC"
    PLATFORM_AUTHENTICATED = "PLATFORM_AUTHENTICATED"
    PROJECT_AUTHORIZED = "PROJECT_AUTHORIZED"


class SubjectKind(StrEnum):
    """Kinds of subjects that may own an assistant execution."""

    GUEST = "GUEST"
    USER = "USER"
    SERVICE = "SERVICE"


class FrozenStrictModel(BaseModel):
    """Base model for immutable, fail-closed runtime domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AuditContext(FrozenStrictModel):
    """Correlation identifiers required on every online AI execution."""

    trace_id: Identifier
    request_id: Identifier


class ProjectExecutionContext(FrozenStrictModel):
    """Server-created scope that constrains one project execution."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    subject_kind: SubjectKind
    subject_id: Identifier
    client_id: Identifier
    deployment_id: Identifier
    deployment_revision_id: Identifier
    assistant_profile_version_id: Identifier
    knowledge_binding_set_id: Identifier
    project_execution_binding_id: Identifier
    project_id: Identifier
    project_version: Identifier
    locale: LocaleTag
    access_segment: AccessSegment
    access_context_hash: AccessContextHash
    knowledge_release_id: Identifier
    authz_epoch: Annotated[int, Field(ge=0, strict=True)]
    issued_at: datetime
    expires_at: datetime
    deadline_at: datetime
    audit: AuditContext

    @field_validator("issued_at", "expires_at", "deadline_at", mode="before")
    @classmethod
    def reject_non_rfc3339_timestamp(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not _RFC3339_TIMESTAMP.fullmatch(value):
            raise ValueError("execution context timestamps must use RFC 3339 strings")
        return value

    @field_validator("issued_at", "expires_at", "deadline_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("execution context timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_time_window(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("execution context expiry must be after issuance")
        if self.deadline_at <= self.issued_at:
            raise ValueError("execution deadline must be after context issuance")
        if self.deadline_at > self.expires_at:
            raise ValueError("execution deadline cannot outlive the execution context")
        return self


class ExecutionContextRejected(RuntimeError):
    """Base error for a structurally valid context that cannot be used."""

    code = "execution_context_rejected"


class ExecutionContextNotYetValid(ExecutionContextRejected):
    code = "execution_context_not_yet_valid"


class ExecutionContextExpired(ExecutionContextRejected):
    code = "execution_context_expired"


class ExecutionDeadlineExceeded(RuntimeError):
    code = "execution_deadline_exceeded"


@dataclass(frozen=True, slots=True)
class GuardedExecutionContext:
    """A context accepted at a specific instant for downstream execution."""

    context: ProjectExecutionContext
    checked_at: datetime
    deadline_remaining: timedelta

    @property
    def deadline_remaining_ms(self) -> int:
        return ceil(self.deadline_remaining.total_seconds() * 1000)


Clock = Callable[[], datetime]

_RFC3339_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionContextGuard:
    """Applies temporal fail-closed checks before any retrieval or model call."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock

    def validate(self, context: ProjectExecutionContext) -> GuardedExecutionContext:
        checked_at = self._clock()
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise RuntimeError("execution context guard clock must include a timezone")
        checked_at = checked_at.astimezone(UTC)

        if context.issued_at > checked_at:
            raise ExecutionContextNotYetValid
        if context.expires_at <= checked_at:
            raise ExecutionContextExpired
        if context.deadline_at <= checked_at:
            raise ExecutionDeadlineExceeded

        return GuardedExecutionContext(
            context=context,
            checked_at=checked_at,
            deadline_remaining=context.deadline_at - checked_at,
        )
