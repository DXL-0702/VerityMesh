"""Fail-closed revocation checks before project retrieval planning."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Protocol, Self

from pydantic import Field, field_validator, model_validator

from .execution_context import (
    AccessContextHash,
    AccessSegment,
    AuditContext,
    Clock,
    ExecutionContextGuard,
    ExecutionDeadlineExceeded,
    FrozenStrictModel,
    GuardedExecutionContext,
    Identifier,
    LocaleTag,
    ProjectExecutionContext,
    SubjectKind,
    utc_now,
)


class RevocationStatus(StrEnum):
    CLEAR = "CLEAR"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


class RevocationScope(FrozenStrictModel):
    """Complete immutable scope covered by one revocation decision."""

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

    @classmethod
    def from_context(cls, context: ProjectExecutionContext) -> Self:
        return cls(
            message_execution_id=context.message_execution_id,
            subject_kind=context.subject_kind,
            subject_id=context.subject_id,
            client_id=context.client_id,
            deployment_id=context.deployment_id,
            deployment_revision_id=context.deployment_revision_id,
            assistant_profile_version_id=context.assistant_profile_version_id,
            knowledge_binding_set_id=context.knowledge_binding_set_id,
            project_execution_binding_id=context.project_execution_binding_id,
            project_id=context.project_id,
            project_version=context.project_version,
            locale=context.locale,
            access_segment=context.access_segment,
            access_context_hash=context.access_context_hash,
            knowledge_release_id=context.knowledge_release_id,
            authz_epoch=context.authz_epoch,
        )


class RevocationCheckResult(FrozenStrictModel):
    """Scoped decision obtained from a known online revocation snapshot."""

    status: RevocationStatus
    scope: RevocationScope
    snapshot_version: Identifier
    checked_at: datetime
    valid_until: datetime

    @field_validator("checked_at", "valid_until")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("revocation timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.valid_until <= self.checked_at:
            raise ValueError("revocation validity must end after the check time")
        return self


@dataclass(frozen=True, slots=True)
class RevocationCheckRequest:
    scope: RevocationScope
    requested_at: datetime
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext


class RevocationCheckerPort(Protocol):
    """Returns a scoped result only when online revocation state can be classified."""

    async def check(self, request: RevocationCheckRequest) -> RevocationCheckResult: ...


class RevocationRejected(RuntimeError):
    code = "revocation_rejected"


class ExecutionRevoked(RevocationRejected):
    code = "execution_revoked"


class RevocationStateUnavailable(RevocationRejected):
    code = "revocation_state_unavailable"


@dataclass(frozen=True, slots=True)
class RevocationClearedExecutionContext:
    """Execution context proven clear against a bounded revocation snapshot."""

    guarded_context: GuardedExecutionContext
    revocation_scope: RevocationScope
    revocation_snapshot_version: Identifier
    revocation_checked_at: datetime
    revocation_valid_until: datetime

    @property
    def context(self) -> ProjectExecutionContext:
        return self.guarded_context.context

    @property
    def checked_at(self) -> datetime:
        return self.guarded_context.checked_at

    @property
    def deadline_remaining(self) -> timedelta:
        return self.guarded_context.deadline_remaining


def revalidate_cleared_execution_context(
    context: RevocationClearedExecutionContext,
    guard: ExecutionContextGuard,
) -> GuardedExecutionContext:
    """Recheck a cleared context immediately before and after downstream work."""

    current = guard.validate(context.context)
    if (
        context.revocation_scope != RevocationScope.from_context(context.context)
        or context.revocation_checked_at > current.checked_at
        or context.revocation_valid_until <= current.checked_at
    ):
        raise RevocationStateUnavailable
    return current


class RevocationGuard:
    """Requires a fresh, scope-matched CLEAR result before downstream execution."""

    def __init__(
        self,
        checker: RevocationCheckerPort,
        *,
        max_clearance_ttl: timedelta,
        clock: Clock = utc_now,
    ) -> None:
        if max_clearance_ttl <= timedelta(0):
            raise ValueError("revocation clearance TTL must be positive")
        self._checker = checker
        self._max_clearance_ttl = max_clearance_ttl
        self._context_guard = ExecutionContextGuard(clock)

    async def validate(
        self,
        guarded_context: GuardedExecutionContext,
    ) -> RevocationClearedExecutionContext:
        current = self._context_guard.validate(guarded_context.context)
        scope = RevocationScope.from_context(current.context)
        request = RevocationCheckRequest(
            scope=scope,
            requested_at=current.checked_at,
            deadline_at=current.context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=current.context.audit,
        )

        try:
            async with asyncio.timeout(request.deadline_remaining.total_seconds()):
                result = await self._checker.check(request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except Exception as error:
            self._context_guard.validate(current.context)
            raise RevocationStateUnavailable from error

        current = self._context_guard.validate(current.context)
        if result.scope != scope:
            raise RevocationStateUnavailable
        if result.checked_at > current.checked_at:
            raise RevocationStateUnavailable
        if result.valid_until <= current.checked_at:
            raise RevocationStateUnavailable
        if result.valid_until - result.checked_at > self._max_clearance_ttl:
            raise RevocationStateUnavailable
        if result.status is RevocationStatus.REVOKED:
            raise ExecutionRevoked
        if result.status is not RevocationStatus.CLEAR:
            raise RevocationStateUnavailable

        return RevocationClearedExecutionContext(
            guarded_context=current,
            revocation_scope=scope,
            revocation_snapshot_version=result.snapshot_version,
            revocation_checked_at=result.checked_at,
            revocation_valid_until=result.valid_until,
        )
