from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from veritymesh_assistant_runtime.execution_context import (
    AccessSegment,
    AuditContext,
    ProjectExecutionContext,
    SubjectKind,
)

NOW = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)


@pytest.fixture
def context_factory() -> Callable[..., ProjectExecutionContext]:
    def build(**overrides: object) -> ProjectExecutionContext:
        values: dict[str, object] = {
            "schema_version": "1.0",
            "message_execution_id": "msg-exec-1",
            "subject_kind": SubjectKind.USER,
            "subject_id": "user-1",
            "client_id": "portal-web",
            "deployment_id": "deployment-1",
            "deployment_revision_id": "deployment-revision-1",
            "assistant_profile_version_id": "profile-version-1",
            "knowledge_binding_set_id": "binding-set-1",
            "project_execution_binding_id": "binding-1",
            "project_id": "project-1",
            "project_version": "1.0.0",
            "locale": "zh-CN",
            "access_segment": AccessSegment.PROJECT_AUTHORIZED,
            "access_context_hash": "a" * 64,
            "knowledge_release_id": "release-1",
            "authz_epoch": 7,
            "issued_at": NOW - timedelta(seconds=1),
            "expires_at": NOW + timedelta(minutes=5),
            "deadline_at": NOW + timedelta(seconds=2),
            "audit": AuditContext(trace_id="trace-1", request_id="request-1"),
        }
        values.update(overrides)
        return ProjectExecutionContext.model_validate(values)

    return build
