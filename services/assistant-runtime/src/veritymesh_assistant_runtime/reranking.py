"""Constrained reranking contracts and deterministic RRF fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Protocol, Self

from pydantic import ValidationError, model_validator

from .execution_context import (
    AuditContext,
    Clock,
    ExecutionContextGuard,
    ExecutionDeadlineExceeded,
    FrozenStrictModel,
    GuardedExecutionContext,
    Identifier,
    utc_now,
)
from .query_planning import (
    ProjectQueryPlan,
    ProjectRetrievalFilter,
    QueryText,
    project_retrieval_filter_from_context,
)
from .retrieval import (
    FiniteScore,
    FusedRetrievalCandidate,
    HybridRetrievalResult,
    PositiveRank,
    ProjectionText,
    RecallBranch,
    RecallProvenance,
    RetrievalExecutionMode,
    Sha256Digest,
    VectorDegradationReason,
    validate_retrieval_chunk_scope,
)
from .revocation import RevocationClearedExecutionContext, revalidate_cleared_execution_context


class RerankingMode(StrEnum):
    RERANKER = "RERANKER"
    RRF_FALLBACK = "RRF_FALLBACK"
    EMPTY = "EMPTY"


class RerankerDegradationReason(StrEnum):
    NONE = "NONE"
    RERANKER_UNAVAILABLE = "RERANKER_UNAVAILABLE"
    RERANKER_CONTRACT_REJECTED = "RERANKER_CONTRACT_REJECTED"


class RerankerBinding(FrozenStrictModel):
    """Trusted logical/physical model identity resolved from the Release Manifest."""

    logical_model: Literal["reranker-primary"]
    provider: Identifier
    region: Identifier
    api_mode: Identifier
    model: Identifier
    revision: Identifier
    configuration_fingerprint: Sha256Digest


class RerankerCandidateInput(FrozenStrictModel):
    """Minimal candidate content allowed to leave the domain kernel."""

    input_rank: PositiveRank
    chunk_id: Identifier
    title: ProjectionText
    section: ProjectionText
    chunk_text: ProjectionText


class RerankerRequest(FrozenStrictModel):
    """Bounded reranker request derived from one retrieval result."""

    normalized_query: QueryText
    message_execution_id: Identifier
    candidate_set_fingerprint: Sha256Digest
    candidates: tuple[RerankerCandidateInput, ...]
    top_k: Literal[10]
    binding: RerankerBinding
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        if not self.candidates:
            raise ValueError("reranker request requires at least one candidate")
        if len(self.candidates) > 50:
            raise ValueError("reranker input cannot exceed RRF Top 50")
        if tuple(item.input_rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("reranker input ranks must be contiguous and start at one")
        if len({item.chunk_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("reranker input cannot repeat a chunk")
        return self


class RerankerResultItem(FrozenStrictModel):
    """Provider-neutral result referring to one input candidate by rank."""

    rank: PositiveRank
    input_rank: PositiveRank
    score: FiniteScore


class RerankerResult(FrozenStrictModel):
    """Provider response before it is applied to trusted retrieval candidates."""

    message_execution_id: Identifier
    candidate_set_fingerprint: Sha256Digest
    binding: RerankerBinding
    items: tuple[RerankerResultItem, ...]

    @model_validator(mode="after")
    def validate_items(self) -> Self:
        if tuple(item.rank for item in self.items) != tuple(range(1, len(self.items) + 1)):
            raise ValueError("reranker result ranks must be contiguous and start at one")
        input_ranks = tuple(item.input_rank for item in self.items)
        if len(set(input_ranks)) != len(input_ranks):
            raise ValueError("reranker result cannot repeat an input rank")
        return self


class RerankerPort(Protocol):
    """Task-semantic port; provider SDK types remain behind its adapter."""

    async def rerank(self, request: RerankerRequest) -> RerankerResult: ...


class RerankingRejected(RuntimeError):
    code = "reranking_rejected"


class RerankingScopeRejected(RerankingRejected):
    code = "reranking_scope_rejected"


class RankedRetrievalCandidate(FrozenStrictModel):
    """Top-10 position while preserving the candidate's original RRF rank."""

    rank: PositiveRank
    candidate: FusedRetrievalCandidate
    reranker_score: FiniteScore | None


class RerankingResult(FrozenStrictModel):
    """Top-10 candidates and complete retrieval/reranker provenance."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    filters: ProjectRetrievalFilter
    retrieval_execution_mode: RetrievalExecutionMode
    vector_degradation_reason: VectorDegradationReason
    bm25_provenance: RecallProvenance
    vector_provenance: RecallProvenance | None
    mode: RerankingMode
    degradation_reason: RerankerDegradationReason
    binding: RerankerBinding | None
    candidates: tuple[RankedRetrievalCandidate, ...]

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if len(self.candidates) > 10:
            raise ValueError("reranking output cannot exceed Top 10")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("reranking output ranks must be contiguous and start at one")
        if len({item.candidate.chunk.chunk_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("reranking output cannot repeat a chunk")
        if len({item.candidate.rank for item in self.candidates}) != len(self.candidates):
            raise ValueError("reranking output cannot repeat an RRF rank")

        hybrid = self.retrieval_execution_mode is RetrievalExecutionMode.HYBRID
        if hybrid != (self.vector_provenance is not None):
            raise ValueError("hybrid retrieval requires vector provenance")
        if hybrid != (self.vector_degradation_reason is VectorDegradationReason.NONE):
            raise ValueError("retrieval mode and vector degradation reason disagree")
        if self.bm25_provenance.branch is not RecallBranch.BM25:
            raise ValueError("BM25 provenance must identify the BM25 branch")
        if self.bm25_provenance.embedding_space_fingerprint is not None:
            raise ValueError("BM25 provenance cannot carry an embedding space")
        if self.vector_provenance is not None:
            if self.vector_provenance.branch is not RecallBranch.VECTOR:
                raise ValueError("vector provenance must identify the vector branch")
            if self.vector_provenance.embedding_space_fingerprint is None:
                raise ValueError("vector provenance requires an embedding space")
            if (
                self.vector_provenance.chunk_manifest_hash
                != self.bm25_provenance.chunk_manifest_hash
            ):
                raise ValueError("retrieval provenance must use one chunk manifest")

        for item in self.candidates:
            validate_retrieval_chunk_scope(
                item.candidate.chunk,
                self.filters,
                expected_manifest_hash=self.bm25_provenance.chunk_manifest_hash,
            )
            if not hybrid and item.candidate.vector_rank is not None:
                raise ValueError("BM25-only reranking cannot contain vector candidates")

        if self.mode is RerankingMode.RERANKER:
            if (
                self.degradation_reason is not RerankerDegradationReason.NONE
                or self.binding is None
                or any(item.reranker_score is None for item in self.candidates)
                or not self.candidates
            ):
                raise ValueError("reranker mode requires a valid binding and scored candidates")
        elif self.mode is RerankingMode.RRF_FALLBACK:
            if (
                self.degradation_reason is RerankerDegradationReason.NONE
                or self.binding is not None
                or any(item.reranker_score is not None for item in self.candidates)
                or not self.candidates
                or any(item.rank != item.candidate.rank for item in self.candidates)
            ):
                raise ValueError("RRF fallback requires an explicit degradation without scores")
        elif (
            self.degradation_reason is not RerankerDegradationReason.NONE
            or self.binding is not None
            or self.candidates
        ):
            raise ValueError("empty reranking must not claim a model call or degradation")
        return self


@dataclass(frozen=True, slots=True)
class RerankingRequest:
    context: RevocationClearedExecutionContext
    plan: ProjectQueryPlan
    retrieval: HybridRetrievalResult
    binding: RerankerBinding


class RerankingKernel:
    """Applies a trusted reranker or returns a bounded RRF Top-10 fallback."""

    def __init__(self, port: RerankerPort, *, clock: Clock = utc_now) -> None:
        self._port = port
        self._context_guard = ExecutionContextGuard(clock)

    async def rerank(self, request: RerankingRequest) -> RerankingResult:
        current, request = self._validate_request(request)
        if not request.retrieval.candidates:
            return self._result(
                request,
                mode=RerankingMode.EMPTY,
                reason=RerankerDegradationReason.NONE,
                binding=None,
                candidates=(),
            )

        context = request.context.context
        port_request = RerankerRequest(
            normalized_query=request.plan.normalized_query,
            message_execution_id=context.message_execution_id,
            candidate_set_fingerprint=reranker_candidate_set_fingerprint(
                request.retrieval.candidates
            ),
            candidates=tuple(
                RerankerCandidateInput(
                    input_rank=item.rank,
                    chunk_id=item.chunk.chunk_id,
                    title=item.chunk.title,
                    section=item.chunk.section,
                    chunk_text=item.chunk.chunk_text,
                )
                for item in request.retrieval.candidates
            ),
            top_k=10,
            binding=request.binding,
            deadline_at=context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=context.audit,
        )
        try:
            async with asyncio.timeout(port_request.deadline_remaining.total_seconds()):
                raw_result = await self._port.rerank(port_request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except Exception:
            self._validate_context(request.context)
            return self._fallback(request, RerankerDegradationReason.RERANKER_UNAVAILABLE)

        self._validate_context(request.context)
        try:
            result = RerankerResult.model_validate(raw_result.model_dump())
            self._validate_provider_result(result, request)
            ranked = self._apply_result(result, request.retrieval.candidates)
        except (AttributeError, TypeError, ValueError, ValidationError):
            return self._fallback(
                request,
                RerankerDegradationReason.RERANKER_CONTRACT_REJECTED,
            )

        return self._result(
            request,
            mode=RerankingMode.RERANKER,
            reason=RerankerDegradationReason.NONE,
            binding=result.binding,
            candidates=ranked,
        )

    def _validate_request(
        self,
        request: RerankingRequest,
    ) -> tuple[GuardedExecutionContext, RerankingRequest]:
        current = self._validate_context(request.context)
        try:
            plan = ProjectQueryPlan.model_validate(request.plan.model_dump())
            retrieval = HybridRetrievalResult.model_validate(request.retrieval.model_dump())
            binding = RerankerBinding.model_validate(request.binding.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise RerankingScopeRejected from error

        validated = RerankingRequest(
            context=request.context,
            plan=plan,
            retrieval=retrieval,
            binding=binding,
        )
        context = request.context.context
        if (
            plan.message_execution_id != context.message_execution_id
            or plan.filters != project_retrieval_filter_from_context(request.context)
            or retrieval.message_execution_id != plan.message_execution_id
            or retrieval.filters != plan.filters
        ):
            raise RerankingScopeRejected
        return current, validated

    def _validate_context(
        self,
        context: RevocationClearedExecutionContext,
    ) -> GuardedExecutionContext:
        return revalidate_cleared_execution_context(context, self._context_guard)

    @staticmethod
    def _validate_provider_result(result: RerankerResult, request: RerankingRequest) -> None:
        expected_size = min(request.plan.limits.reranker_top_k, len(request.retrieval.candidates))
        allowed = {candidate.rank for candidate in request.retrieval.candidates}
        if result.binding != request.binding:
            raise ValueError("reranker result binding does not match the trusted request")
        if (
            result.message_execution_id != request.plan.message_execution_id
            or result.candidate_set_fingerprint
            != reranker_candidate_set_fingerprint(request.retrieval.candidates)
        ):
            raise ValueError("reranker result does not match the candidate set")
        if len(result.items) != expected_size:
            raise ValueError("reranker result does not contain the expected Top-K")
        if any(item.input_rank not in allowed for item in result.items):
            raise ValueError("reranker result references an unknown candidate")

    @staticmethod
    def _apply_result(
        result: RerankerResult,
        candidates: tuple[FusedRetrievalCandidate, ...],
    ) -> tuple[RankedRetrievalCandidate, ...]:
        by_rank = {candidate.rank: candidate for candidate in candidates}
        return tuple(
            RankedRetrievalCandidate(
                rank=item.rank,
                candidate=by_rank[item.input_rank],
                reranker_score=item.score,
            )
            for item in result.items
        )

    def _fallback(
        self,
        request: RerankingRequest,
        reason: RerankerDegradationReason,
    ) -> RerankingResult:
        self._validate_context(request.context)
        return self._result(
            request,
            mode=RerankingMode.RRF_FALLBACK,
            reason=reason,
            binding=None,
            candidates=tuple(
                RankedRetrievalCandidate(
                    rank=rank,
                    candidate=candidate,
                    reranker_score=None,
                )
                for rank, candidate in enumerate(request.retrieval.candidates[:10], start=1)
            ),
        )

    @staticmethod
    def _result(
        request: RerankingRequest,
        *,
        mode: RerankingMode,
        reason: RerankerDegradationReason,
        binding: RerankerBinding | None,
        candidates: tuple[RankedRetrievalCandidate, ...],
    ) -> RerankingResult:
        retrieval = request.retrieval
        return RerankingResult(
            schema_version="1.0",
            message_execution_id=retrieval.message_execution_id,
            filters=retrieval.filters,
            retrieval_execution_mode=retrieval.execution_mode,
            vector_degradation_reason=retrieval.vector_degradation_reason,
            bm25_provenance=retrieval.bm25_provenance,
            vector_provenance=retrieval.vector_provenance,
            mode=mode,
            degradation_reason=reason,
            binding=binding,
            candidates=candidates,
        )


def reranker_candidate_set_fingerprint(
    candidates: tuple[FusedRetrievalCandidate, ...],
) -> str:
    payload = "\n".join(
        "\x1f".join(
            (
                str(candidate.rank),
                candidate.chunk.chunk_id,
                candidate.chunk.knowledge_revision_id,
                candidate.chunk.content_hash,
            )
        )
        for candidate in candidates
    )
    return sha256(payload.encode("utf-8")).hexdigest()
