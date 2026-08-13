import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from support.query_planner import ScriptedQueryPlanner
from veritymesh_assistant_runtime.execution_context import (
    ExecutionContextGuard,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.query_planning import (
    MAX_QUERY_CHARACTERS,
    DeterministicProjectQueryPlanner,
    EmptyProjectQuery,
    InvalidProjectQuery,
    ProjectQueryPlan,
    ProjectQueryTooLarge,
    QueryPlannerPort,
    QueryPlanningRequest,
    normalize_query,
)
from veritymesh_assistant_runtime.revocation import (
    RevocationClearedExecutionContext,
    RevocationScope,
)

RAW_QUERY = "  \uff21\uff30\uff29\t错误\n怎么处理\uff1f  "


def planning_request(
    context_factory: Callable[..., ProjectExecutionContext],
    original_query: str = RAW_QUERY,
) -> QueryPlanningRequest:
    guarded = ExecutionContextGuard(lambda: NOW).validate(context_factory())
    context = RevocationClearedExecutionContext(
        guarded_context=guarded,
        revocation_scope=RevocationScope.from_context(guarded.context),
        revocation_snapshot_version="revocation-snapshot-7",
        revocation_checked_at=NOW,
        revocation_valid_until=NOW + timedelta(seconds=10),
    )
    return QueryPlanningRequest(context=context, original_query=original_query)


def deterministic_plan(request: QueryPlanningRequest) -> ProjectQueryPlan:
    return asyncio.run(DeterministicProjectQueryPlanner().plan(request))


def test_deterministic_plan_derives_all_scope_from_the_guarded_context(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = planning_request(context_factory)

    plan = deterministic_plan(request)

    assert plan.schema_version == "1.0"
    assert plan.planner_strategy == "DETERMINISTIC_V1"
    assert plan.intent == "KNOWLEDGE_QUERY"
    assert plan.original_query == RAW_QUERY
    assert plan.normalized_query == "API 错误 怎么处理?"
    assert plan.locale == request.context.context.locale
    assert plan.retrieval_mode == "HYBRID"
    assert plan.filters.project_execution_binding_id == "binding-1"
    assert plan.filters.project_id == "project-1"
    assert plan.filters.project_version == "1.0.0"
    assert plan.filters.locale == "zh-CN"
    assert plan.filters.access_segment == "PROJECT_AUTHORIZED"
    assert plan.filters.access_context_hash == "a" * 64
    assert plan.filters.knowledge_release_id == "release-1"
    assert plan.filters.revocation_snapshot_version == "revocation-snapshot-7"
    assert plan.filters.revocation_valid_until == NOW + timedelta(seconds=10)
    assert plan.filters.effective_at == NOW
    assert plan.limits.model_dump() == {
        "bm25_top_k": 50,
        "vector_top_k": 50,
        "rrf_k": 60,
        "fused_top_k": 50,
        "reranker_top_k": 10,
    }
    assert plan.required_evidence.citation_required is True
    assert plan.required_evidence.claim_grounding_required is True
    assert plan.clarification_needed is False
    assert plan.clarification_question is None
    assert {"index", "model_id", "sql"}.isdisjoint(plan.model_dump())

    values = plan.model_dump()
    values["retrieval_mode"] = "BM25_ONLY"
    with pytest.raises(ValidationError):
        ProjectQueryPlan.model_validate(values)


@pytest.mark.parametrize(
    ("query", "error_type"),
    [
        ("", EmptyProjectQuery),
        (" \t\n ", EmptyProjectQuery),
        ("a" * (MAX_QUERY_CHARACTERS + 1), ProjectQueryTooLarge),
        ("\x00", InvalidProjectQuery),
        (cast(str, 42), InvalidProjectQuery),
        ("\ufdfa" * MAX_QUERY_CHARACTERS, ProjectQueryTooLarge),
    ],
)
def test_query_normalization_rejects_ambiguous_or_unbounded_input(
    query: str,
    error_type: type[ValueError],
) -> None:
    with pytest.raises(error_type):
        normalize_query(query)


@pytest.mark.parametrize(
    ("clarification_needed", "clarification_question", "message"),
    [
        (True, None, "required when clarification is needed"),
        (False, "Which project?", "forbidden when clarification is not needed"),
    ],
)
def test_query_plan_enforces_clarification_consistency(
    context_factory: Callable[..., ProjectExecutionContext],
    clarification_needed: bool,
    clarification_question: str | None,
    message: str,
) -> None:
    values = deterministic_plan(planning_request(context_factory)).model_dump()
    values["clarification_needed"] = clarification_needed
    values["clarification_question"] = clarification_question

    with pytest.raises(ValidationError, match=message):
        ProjectQueryPlan.model_validate(values)


def test_scripted_planner_records_calls_and_replays_plans_and_failures(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = planning_request(context_factory, "Where is the API guide?")
    expected_plan = deterministic_plan(request)
    expected_failure = RuntimeError("provider unavailable")
    planner: QueryPlannerPort = ScriptedQueryPlanner([expected_plan, expected_failure])

    assert asyncio.run(planner.plan(request)) is expected_plan
    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(planner.plan(request))
    with pytest.raises(AssertionError, match="no remaining outcome"):
        asyncio.run(planner.plan(request))
    assert cast(ScriptedQueryPlanner, planner).requests == [request, request, request]
