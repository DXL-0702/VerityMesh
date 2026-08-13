from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from conftest import NOW
from pydantic import ValidationError
from veritymesh_assistant_runtime.execution_context import (
    ExecutionContextExpired,
    ExecutionContextGuard,
    ExecutionContextNotYetValid,
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
)


def test_guard_accepts_a_current_immutable_context(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    context = context_factory(subject_id="issuer.example/users/user|42")

    guarded = ExecutionContextGuard(lambda: NOW).validate(context)

    assert guarded.context is context
    assert guarded.checked_at == NOW
    assert guarded.deadline_remaining == timedelta(seconds=2)
    assert guarded.deadline_remaining_ms == 2000
    with pytest.raises(ValidationError):
        context.project_id = "another-project"


def test_default_guard_uses_an_aware_utc_clock(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    now = datetime.now(UTC)
    context = context_factory(
        issued_at=now - timedelta(seconds=1),
        deadline_at=now + timedelta(seconds=5),
        expires_at=now + timedelta(seconds=10),
    )

    assert ExecutionContextGuard().validate(context).deadline_remaining_ms > 0


@pytest.mark.parametrize(
    ("overrides", "error_type"),
    [
        ({"issued_at": NOW + timedelta(seconds=1)}, ExecutionContextNotYetValid),
        (
            {
                "issued_at": NOW - timedelta(minutes=2),
                "deadline_at": NOW - timedelta(seconds=2),
                "expires_at": NOW - timedelta(seconds=1),
            },
            ExecutionContextExpired,
        ),
        ({"deadline_at": NOW}, ExecutionDeadlineExceeded),
    ],
)
def test_guard_rejects_unusable_time_windows(
    context_factory: Callable[..., ProjectExecutionContext],
    overrides: dict[str, object],
    error_type: type[RuntimeError],
) -> None:
    with pytest.raises(error_type):
        ExecutionContextGuard(lambda: NOW).validate(context_factory(**overrides))


def test_guard_rejects_a_naive_clock(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    with pytest.raises(RuntimeError, match="clock must include a timezone"):
        ExecutionContextGuard(lambda: datetime(2026, 8, 11, 8, 0)).validate(context_factory())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"issued_at": 1786435199}, "timestamps must use RFC 3339 strings"),
        ({"issued_at": datetime(2026, 8, 11, 7, 59, 59)}, "must include a timezone"),
        (
            {"expires_at": NOW - timedelta(seconds=2)},
            "expiry must be after issuance",
        ),
        ({"deadline_at": NOW - timedelta(seconds=2)}, "deadline must be after context issuance"),
        (
            {"deadline_at": NOW + timedelta(minutes=6)},
            "deadline cannot outlive the execution context",
        ),
        ({"locale": "not_a_locale"}, "String should match pattern"),
        ({"unknown_scope": "forbidden"}, "Extra inputs are not permitted"),
    ],
)
def test_context_rejects_invalid_or_ambiguous_values(
    context_factory: Callable[..., ProjectExecutionContext],
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        context_factory(**overrides)
