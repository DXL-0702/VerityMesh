"""Deterministic project query planning and the model task-port boundary."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from .execution_context import (
    AccessContextHash,
    AccessSegment,
    FrozenStrictModel,
    Identifier,
    LocaleTag,
)
from .revocation import RevocationClearedExecutionContext

MAX_QUERY_CHARACTERS = 8192

QueryText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=MAX_QUERY_CHARACTERS),
]


class QueryIntent(StrEnum):
    KNOWLEDGE_QUERY = "KNOWLEDGE_QUERY"


class RetrievalMode(StrEnum):
    HYBRID = "HYBRID"


class ProjectRetrievalFilter(FrozenStrictModel):
    """Trusted scope applied before every retrieval branch executes Top-K."""

    project_execution_binding_id: Identifier
    project_id: Identifier
    project_version: Identifier
    locale: LocaleTag
    access_segment: AccessSegment
    access_context_hash: AccessContextHash
    knowledge_release_id: Identifier
    revocation_snapshot_version: Identifier
    revocation_valid_until: datetime
    effective_at: datetime


def project_retrieval_filter_from_context(
    context: RevocationClearedExecutionContext,
) -> ProjectRetrievalFilter:
    """Derive the only retrieval filter accepted for a cleared execution."""

    execution = context.context
    return ProjectRetrievalFilter(
        project_execution_binding_id=execution.project_execution_binding_id,
        project_id=execution.project_id,
        project_version=execution.project_version,
        locale=execution.locale,
        access_segment=execution.access_segment,
        access_context_hash=execution.access_context_hash,
        knowledge_release_id=execution.knowledge_release_id,
        revocation_snapshot_version=context.revocation_snapshot_version,
        revocation_valid_until=context.revocation_valid_until,
        effective_at=context.checked_at,
    )


class RetrievalLimits(FrozenStrictModel):
    """Frozen first-stage retrieval and fusion limits."""

    bm25_top_k: Literal[50] = 50
    vector_top_k: Literal[50] = 50
    rrf_k: Literal[60] = 60
    fused_top_k: Literal[50] = 50
    reranker_top_k: Literal[10] = 10


class RequiredEvidence(FrozenStrictModel):
    """Output gates that a query plan cannot weaken."""

    citation_required: Literal[True] = True
    claim_grounding_required: Literal[True] = True


class ProjectQueryPlan(FrozenStrictModel):
    """Validated plan assembled around a server-derived retrieval scope."""

    schema_version: Literal["1.0"]
    planner_strategy: Literal["DETERMINISTIC_V1"]
    message_execution_id: Identifier
    intent: QueryIntent
    original_query: QueryText
    normalized_query: QueryText
    locale: LocaleTag
    retrieval_mode: RetrievalMode
    filters: ProjectRetrievalFilter
    limits: RetrievalLimits = Field(default_factory=RetrievalLimits)
    required_evidence: RequiredEvidence = Field(default_factory=RequiredEvidence)
    clarification_needed: bool
    clarification_question: QueryText | None

    @model_validator(mode="after")
    def validate_clarification(self) -> Self:
        if self.clarification_needed and self.clarification_question is None:
            raise ValueError("a clarification question is required when clarification is needed")
        if not self.clarification_needed and self.clarification_question is not None:
            raise ValueError(
                "a clarification question is forbidden when clarification is not needed"
            )
        return self


@dataclass(frozen=True, slots=True)
class QueryPlanningRequest:
    context: RevocationClearedExecutionContext
    original_query: str


class QueryPlannerPort(Protocol):
    """Task-semantic port implemented by deterministic or model-backed planners."""

    async def plan(self, request: QueryPlanningRequest) -> ProjectQueryPlan: ...


class ProjectQueryRejected(ValueError):
    code = "project_query_rejected"


class InvalidProjectQuery(ProjectQueryRejected):
    code = "invalid_project_query"


class EmptyProjectQuery(ProjectQueryRejected):
    code = "empty_project_query"


class ProjectQueryTooLarge(ProjectQueryRejected):
    code = "project_query_too_large"


_WHITESPACE = re.compile(r"\s+")


def normalize_query(original_query: str) -> str:
    """Normalize only the retrieval form while preserving the original input."""

    if not isinstance(original_query, str):
        raise InvalidProjectQuery
    if len(original_query) > MAX_QUERY_CHARACTERS:
        raise ProjectQueryTooLarge

    normalized_query = unicodedata.normalize("NFKC", original_query)
    normalized_query = _WHITESPACE.sub(" ", normalized_query).strip()
    if not normalized_query:
        raise EmptyProjectQuery
    if any(unicodedata.category(character) == "Cc" for character in normalized_query):
        raise InvalidProjectQuery
    if len(normalized_query) > MAX_QUERY_CHARACTERS:
        raise ProjectQueryTooLarge
    return normalized_query


class DeterministicProjectQueryPlanner:
    """Build the safe default plan without invoking any model provider."""

    async def plan(self, request: QueryPlanningRequest) -> ProjectQueryPlan:
        normalized_query = normalize_query(request.original_query)
        guarded = request.context
        context = guarded.context

        return ProjectQueryPlan(
            schema_version="1.0",
            planner_strategy="DETERMINISTIC_V1",
            message_execution_id=context.message_execution_id,
            intent=QueryIntent.KNOWLEDGE_QUERY,
            original_query=request.original_query,
            normalized_query=normalized_query,
            locale=context.locale,
            retrieval_mode=RetrievalMode.HYBRID,
            filters=project_retrieval_filter_from_context(guarded),
            clarification_needed=False,
            clarification_question=None,
        )
