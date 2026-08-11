import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from support.revocation import ScriptedRevocationChecker
from veritymesh_assistant_runtime.execution_context import (
    ExecutionContextGuard,
    ExecutionDeadlineExceeded,
    GuardedExecutionContext,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.revocation import (
    ExecutionRevoked,
    RevocationCheckerPort,
    RevocationCheckRequest,
    RevocationCheckResult,
    RevocationGuard,
    RevocationScope,
    RevocationStateUnavailable,
    RevocationStatus,
)

MAX_CLEARANCE_TTL = timedelta(seconds=30)


class CancelledRevocationChecker:
    async def check(self, _request: RevocationCheckRequest) -> RevocationCheckResult:
        raise asyncio.CancelledError


def guarded_context(
    context_factory: Callable[..., ProjectExecutionContext],
) -> GuardedExecutionContext:
    return ExecutionContextGuard(lambda: NOW).validate(context_factory())


def check_result(
    guarded: GuardedExecutionContext,
    *,
    status: RevocationStatus = RevocationStatus.CLEAR,
    scope: RevocationScope | None = None,
    checked_at: datetime = NOW,
    valid_until: datetime = NOW + timedelta(seconds=10),
) -> RevocationCheckResult:
    return RevocationCheckResult(
        status=status,
        scope=scope or RevocationScope.from_context(guarded.context),
        snapshot_version="revocation-snapshot-7",
        checked_at=checked_at,
        valid_until=valid_until,
    )


def revocation_guard(
    checker: RevocationCheckerPort,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
) -> RevocationGuard:
    return RevocationGuard(
        checker,
        max_clearance_ttl=MAX_CLEARANCE_TTL,
        clock=clock,
    )


def test_clear_result_produces_a_scope_bound_execution_context(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)
    result = check_result(guarded)
    checker = ScriptedRevocationChecker([result])

    cleared = asyncio.run(revocation_guard(checker).validate(guarded))

    assert cleared.context is guarded.context
    assert cleared.checked_at == NOW
    assert cleared.deadline_remaining == timedelta(seconds=2)
    assert cleared.revocation_scope == RevocationScope.from_context(guarded.context)
    assert cleared.revocation_snapshot_version == "revocation-snapshot-7"
    assert cleared.revocation_checked_at == NOW
    assert cleared.revocation_valid_until == NOW + timedelta(seconds=10)
    assert checker.requests == [
        RevocationCheckRequest(
            scope=cleared.revocation_scope,
            requested_at=NOW,
            deadline_at=guarded.context.deadline_at,
            deadline_remaining=timedelta(seconds=2),
            audit=guarded.context.audit,
        )
    ]


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (RevocationStatus.REVOKED, ExecutionRevoked),
        (RevocationStatus.UNKNOWN, RevocationStateUnavailable),
    ],
)
def test_non_clear_results_fail_closed(
    context_factory: Callable[..., ProjectExecutionContext],
    status: RevocationStatus,
    error_type: type[RuntimeError],
) -> None:
    guarded = guarded_context(context_factory)
    checker = ScriptedRevocationChecker([check_result(guarded, status=status)])

    with pytest.raises(error_type):
        asyncio.run(revocation_guard(checker).validate(guarded))


@pytest.mark.parametrize("invalid_result", ["scope", "future", "expired", "oversized_ttl"])
def test_invalid_or_stale_results_fail_closed(
    context_factory: Callable[..., ProjectExecutionContext],
    invalid_result: str,
) -> None:
    guarded = guarded_context(context_factory)
    result = check_result(guarded)
    if invalid_result == "scope":
        mismatched_values = result.scope.model_dump()
        mismatched_values["project_id"] = "another-project"
        result = check_result(guarded, scope=RevocationScope.model_validate(mismatched_values))
    elif invalid_result == "future":
        result = check_result(
            guarded,
            checked_at=NOW + timedelta(seconds=1),
            valid_until=NOW + timedelta(seconds=2),
        )
    elif invalid_result == "expired":
        result = check_result(
            guarded,
            checked_at=NOW - timedelta(seconds=2),
            valid_until=NOW,
        )
    else:
        result = check_result(guarded, valid_until=NOW + MAX_CLEARANCE_TTL + timedelta(seconds=1))

    with pytest.raises(RevocationStateUnavailable):
        asyncio.run(revocation_guard(ScriptedRevocationChecker([result])).validate(guarded))


def test_checker_failures_and_exhausted_test_doubles_are_fail_closed(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)
    failure = RuntimeError("revocation store unavailable")
    checker = ScriptedRevocationChecker([failure])

    with pytest.raises(RevocationStateUnavailable) as raised:
        asyncio.run(revocation_guard(checker).validate(guarded))
    assert raised.value.__cause__ is failure

    request = checker.requests[0]
    with pytest.raises(AssertionError, match="no remaining outcome"):
        asyncio.run(checker.check(request))


def test_deadline_is_rechecked_after_the_revocation_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)
    checker = ScriptedRevocationChecker([check_result(guarded)])
    clock_values = iter([NOW, NOW + timedelta(seconds=3)])

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(revocation_guard(checker, clock=lambda: next(clock_values)).validate(guarded))
    assert len(checker.requests) == 1


def test_expired_deadline_prevents_the_revocation_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)
    checker = ScriptedRevocationChecker([check_result(guarded)])

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(
            revocation_guard(checker, clock=lambda: NOW + timedelta(seconds=3)).validate(guarded)
        )
    assert checker.requests == []


def test_deadline_takes_precedence_when_the_revocation_call_fails_late(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)
    checker = ScriptedRevocationChecker([RuntimeError("revocation store timed out")])
    clock_values = iter([NOW, NOW + timedelta(seconds=3)])

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(revocation_guard(checker, clock=lambda: next(clock_values)).validate(guarded))
    assert len(checker.requests) == 1


def test_cancellation_is_not_converted_into_an_unknown_revocation_state(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(revocation_guard(CancelledRevocationChecker()).validate(guarded))


def test_revocation_result_requires_an_aware_ordered_time_window(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    guarded = guarded_context(context_factory)
    values = check_result(guarded).model_dump()
    values["checked_at"] = datetime(2026, 8, 11, 8, 0)

    with pytest.raises(ValidationError, match="must include a timezone"):
        RevocationCheckResult.model_validate(values)

    values["checked_at"] = NOW
    values["valid_until"] = NOW
    with pytest.raises(ValidationError, match="must end after the check time"):
        RevocationCheckResult.model_validate(values)


def test_revocation_guard_requires_a_positive_clearance_ttl() -> None:
    checker = cast(RevocationCheckerPort, ScriptedRevocationChecker([]))

    with pytest.raises(ValueError, match="TTL must be positive"):
        RevocationGuard(checker, max_clearance_ttl=timedelta(0))
