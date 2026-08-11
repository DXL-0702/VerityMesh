"""Constrained hybrid retrieval contracts and deterministic domain fusion."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from .execution_context import (
    AccessSegment,
    AuditContext,
    Clock,
    ExecutionContextGuard,
    FrozenStrictModel,
    GuardedExecutionContext,
    Identifier,
    LocaleTag,
    utc_now,
)
from .query_planning import ProjectQueryPlan, ProjectRetrievalFilter, QueryText
from .revocation import (
    RevocationClearedExecutionContext,
    RevocationScope,
    RevocationStateUnavailable,
)

Sha256Digest = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]
ProjectionText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=131_072),
]
CitationUrl = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=2_048, pattern=r"^\S+$"),
]
FiniteScore = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveRank = Annotated[int, Field(ge=1, strict=True)]
PositiveTopK = Annotated[int, Field(ge=1, strict=True)]


class RecallBranch(StrEnum):
    BM25 = "BM25"
    VECTOR = "VECTOR"


class RetrievalExecutionMode(StrEnum):
    HYBRID = "HYBRID"
    BM25_ONLY = "BM25_ONLY"


class VectorDegradationReason(StrEnum):
    NONE = "NONE"
    QUERY_EMBEDDING_UNAVAILABLE = "QUERY_EMBEDDING_UNAVAILABLE"
    QUERY_EMBEDDING_CONTRACT_REJECTED = "QUERY_EMBEDDING_CONTRACT_REJECTED"
    VECTOR_RECALL_UNAVAILABLE = "VECTOR_RECALL_UNAVAILABLE"
    VECTOR_CONTRACT_REJECTED = "VECTOR_CONTRACT_REJECTED"


class EmbeddingSpaceFingerprint(FrozenStrictModel):
    """Complete identity and numeric contract for one immutable vector space."""

    fingerprint: Sha256Digest
    dimension: Annotated[int, Field(ge=1, strict=True)]
    distance: Literal["COSINE"] = "COSINE"
    normalized: Literal[True] = True
    vector_data_type: Literal["FLOAT32"] = "FLOAT32"


class QueryEmbeddingResult(FrozenStrictModel):
    """One query vector with the exact space used to produce it."""

    vector: tuple[FiniteScore, ...]
    embedding_space_fingerprint: EmbeddingSpaceFingerprint

    @model_validator(mode="after")
    def validate_vector_contract(self) -> Self:
        if len(self.vector) != self.embedding_space_fingerprint.dimension:
            raise ValueError("query vector dimension does not match its embedding space")
        norm = math.sqrt(math.fsum(value * value for value in self.vector))
        if not 0.999 <= norm <= 1.001:
            raise ValueError("query vector is not L2-normalized")
        return self


class RetrievalChunk(FrozenStrictModel):
    """Minimal serving projection needed by reranking and evidence validation."""

    chunk_id: Identifier
    document_id: Identifier
    knowledge_revision_id: Identifier
    knowledge_space_id: Identifier
    project_id: Identifier
    project_version: Identifier
    locale: LocaleTag
    access_segment: AccessSegment
    knowledge_release_id: Identifier
    content_hash: Sha256Digest
    chunk_manifest_hash: Sha256Digest
    title: ProjectionText
    section: ProjectionText
    chunk_text: ProjectionText
    citation_url: CitationUrl
    start_char: Annotated[int, Field(ge=0, strict=True)]
    end_char: Annotated[int, Field(ge=1, strict=True)]
    effective_from: datetime | None
    effective_to: datetime | None

    @field_validator("effective_from", "effective_to")
    @classmethod
    def normalize_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("chunk effective timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.end_char <= self.start_char:
            raise ValueError("chunk end offset must be after its start offset")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("chunk effective window must be ordered")
        return self


class RecallHit(FrozenStrictModel):
    """A storage-native score and rank over a safe chunk projection."""

    chunk: RetrievalChunk
    rank: PositiveRank
    score: FiniteScore
    highlight: ProjectionText | None = None


class RecallResult(FrozenStrictModel):
    """Self-describing result returned by one independent recall adapter."""

    schema_version: Literal["1.0"]
    branch: RecallBranch
    filters: ProjectRetrievalFilter
    message_execution_id: Identifier
    projection_watermark: Identifier
    chunk_manifest_hash: Sha256Digest
    projection_configuration_fingerprint: Sha256Digest
    embedding_space_fingerprint: EmbeddingSpaceFingerprint | None
    hits: tuple[RecallHit, ...]

    @model_validator(mode="after")
    def validate_result_contract(self) -> Self:
        has_vector_space = self.embedding_space_fingerprint is not None
        if has_vector_space != (self.branch is RecallBranch.VECTOR):
            raise ValueError("only vector recall may carry an embedding space fingerprint")

        expected_ranks = tuple(range(1, len(self.hits) + 1))
        if tuple(hit.rank for hit in self.hits) != expected_ranks:
            raise ValueError("recall ranks must be contiguous and start at one")
        if len({hit.chunk.chunk_id for hit in self.hits}) != len(self.hits):
            raise ValueError("recall results cannot repeat a chunk")

        for hit in self.hits:
            chunk = hit.chunk
            if chunk.chunk_manifest_hash != self.chunk_manifest_hash:
                raise ValueError("recall chunk does not match the result manifest")
            if (
                chunk.project_id,
                chunk.project_version,
                chunk.locale,
                chunk.knowledge_release_id,
            ) != (
                self.filters.project_id,
                self.filters.project_version,
                self.filters.locale,
                self.filters.knowledge_release_id,
            ):
                raise ValueError("recall chunk does not match the project retrieval scope")
            if chunk.access_segment is not self.filters.access_segment:
                raise ValueError("recall chunk does not match the access segment")
            if (
                chunk.effective_from is not None
                and self.filters.effective_at < chunk.effective_from
            ):
                raise ValueError("recall chunk is not effective yet")
            if chunk.effective_to is not None and self.filters.effective_at >= chunk.effective_to:
                raise ValueError("recall chunk is no longer effective")
            if self.branch is RecallBranch.VECTOR and hit.highlight is not None:
                raise ValueError("vector recall cannot return a lexical highlight")
        return self


class RecallProjectionExpectation(FrozenStrictModel):
    """Trusted release metadata an adapter must select and echo exactly."""

    projection_watermark: Identifier
    chunk_manifest_hash: Sha256Digest
    projection_configuration_fingerprint: Sha256Digest


class RetrievalProjectionSet(FrozenStrictModel):
    """Jointly activated BM25 and Vector projections for one release."""

    knowledge_release_id: Identifier
    bm25: RecallProjectionExpectation
    vector: RecallProjectionExpectation
    embedding_space_fingerprint: EmbeddingSpaceFingerprint

    @model_validator(mode="after")
    def validate_joint_manifest(self) -> Self:
        if self.bm25.chunk_manifest_hash != self.vector.chunk_manifest_hash:
            raise ValueError("joint retrieval projections must use the same chunk manifest")
        return self


@dataclass(frozen=True, slots=True)
class QueryEmbeddingRequest:
    normalized_query: QueryText
    locale: LocaleTag
    expected_embedding_space_fingerprint: EmbeddingSpaceFingerprint
    message_execution_id: Identifier
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext


@dataclass(frozen=True, slots=True)
class Bm25RecallRequest:
    normalized_query: QueryText
    filters: ProjectRetrievalFilter
    projection: RecallProjectionExpectation
    top_k: PositiveTopK
    message_execution_id: Identifier
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext


@dataclass(frozen=True, slots=True)
class VectorRecallRequest:
    query_vector: tuple[FiniteScore, ...]
    embedding_space_fingerprint: EmbeddingSpaceFingerprint
    filters: ProjectRetrievalFilter
    projection: RecallProjectionExpectation
    top_k: PositiveTopK
    message_execution_id: Identifier
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext


class QueryEmbeddingPort(Protocol):
    """Produces a query vector without exposing provider SDK types."""

    async def embed_query(self, request: QueryEmbeddingRequest) -> QueryEmbeddingResult: ...


class Bm25RecallPort(Protocol):
    """Performs scope-filtered lexical Top-K before returning any hit."""

    async def recall(self, request: Bm25RecallRequest) -> RecallResult: ...


class VectorRecallPort(Protocol):
    """Performs scope- and vector-space-filtered dense Top-K."""

    async def recall(self, request: VectorRecallRequest) -> RecallResult: ...


class RetrievalRejected(RuntimeError):
    code = "retrieval_rejected"


class RetrievalScopeRejected(RetrievalRejected):
    code = "retrieval_scope_rejected"


class Bm25RecallUnavailable(RetrievalRejected):
    code = "bm25_recall_unavailable"


class Bm25RecallContractRejected(RetrievalRejected):
    code = "bm25_recall_contract_rejected"


class RetrievalProjectionConflict(RetrievalRejected):
    code = "retrieval_projection_conflict"


class InvalidFusionConfiguration(ValueError):
    code = "invalid_fusion_configuration"


class FusedRetrievalCandidate(FrozenStrictModel):
    """One stable RRF candidate with both branches' native evidence retained."""

    rank: PositiveRank
    rrf_score: FiniteScore
    chunk: RetrievalChunk
    bm25_rank: PositiveRank | None
    bm25_score: FiniteScore | None
    bm25_highlight: ProjectionText | None
    vector_rank: PositiveRank | None
    vector_score: FiniteScore | None

    @model_validator(mode="after")
    def validate_branch_fields(self) -> Self:
        bm25_present = self.bm25_rank is not None and self.bm25_score is not None
        vector_present = self.vector_rank is not None and self.vector_score is not None
        if not bm25_present and not vector_present:
            raise ValueError("a fused candidate must originate from at least one branch")
        if (self.bm25_rank is None) != (self.bm25_score is None):
            raise ValueError("BM25 rank and score must be present together")
        if (self.vector_rank is None) != (self.vector_score is None):
            raise ValueError("vector rank and score must be present together")
        if self.bm25_highlight is not None and not bm25_present:
            raise ValueError("a lexical highlight requires a BM25 candidate")
        return self


class RecallProvenance(FrozenStrictModel):
    """Projection identity retained for audit without exposing physical storage."""

    branch: RecallBranch
    projection_watermark: Identifier
    chunk_manifest_hash: Sha256Digest
    projection_configuration_fingerprint: Sha256Digest
    embedding_space_fingerprint: EmbeddingSpaceFingerprint | None


class HybridRetrievalResult(FrozenStrictModel):
    """Domain-fused retrieval output ready for reranking."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    filters: ProjectRetrievalFilter
    execution_mode: RetrievalExecutionMode
    vector_degradation_reason: VectorDegradationReason
    bm25_provenance: RecallProvenance
    vector_provenance: RecallProvenance | None
    candidates: tuple[FusedRetrievalCandidate, ...]

    @model_validator(mode="after")
    def validate_execution_mode(self) -> Self:
        hybrid = self.execution_mode is RetrievalExecutionMode.HYBRID
        if hybrid != (self.vector_provenance is not None):
            raise ValueError("hybrid retrieval requires vector provenance")
        if hybrid != (self.vector_degradation_reason is VectorDegradationReason.NONE):
            raise ValueError("retrieval mode and vector degradation reason disagree")
        if self.bm25_provenance.branch is not RecallBranch.BM25:
            raise ValueError("BM25 provenance must identify the BM25 branch")
        if (
            self.vector_provenance is not None
            and self.vector_provenance.branch is not RecallBranch.VECTOR
        ):
            raise ValueError("vector provenance must identify the vector branch")
        if tuple(candidate.rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("fused ranks must be contiguous and start at one")
        return self


@dataclass(frozen=True, slots=True)
class HybridRetrievalRequest:
    context: RevocationClearedExecutionContext
    plan: ProjectQueryPlan
    projections: RetrievalProjectionSet


@dataclass(frozen=True, slots=True)
class _VectorBranchResult:
    result: RecallResult | None
    degradation_reason: VectorDegradationReason


@dataclass(slots=True)
class _FusionRecord:
    chunk: RetrievalChunk
    bm25_rank: int | None = None
    bm25_score: float | None = None
    bm25_highlight: str | None = None
    vector_rank: int | None = None
    vector_score: float | None = None


def reciprocal_rank_fusion(
    bm25: RecallResult,
    vector: RecallResult | None,
    *,
    k: int,
    top_k: int,
) -> tuple[FusedRetrievalCandidate, ...]:
    """Fuse independent ranks without comparing storage-native scores."""

    if k <= 0 or top_k <= 0:
        raise InvalidFusionConfiguration("RRF k and top_k must be positive")

    records: dict[str, _FusionRecord] = {}
    for hit in bm25.hits:
        records[hit.chunk.chunk_id] = _FusionRecord(
            chunk=hit.chunk,
            bm25_rank=hit.rank,
            bm25_score=hit.score,
            bm25_highlight=hit.highlight,
        )

    if vector is not None:
        for hit in vector.hits:
            existing = records.get(hit.chunk.chunk_id)
            if existing is None:
                records[hit.chunk.chunk_id] = _FusionRecord(
                    chunk=hit.chunk,
                    vector_rank=hit.rank,
                    vector_score=hit.score,
                )
                continue
            if existing.chunk != hit.chunk:
                raise RetrievalProjectionConflict
            existing.vector_rank = hit.rank
            existing.vector_score = hit.score

    scored = [
        (
            math.fsum(
                contribution
                for contribution in (
                    1.0 / (k + record.bm25_rank) if record.bm25_rank is not None else None,
                    1.0 / (k + record.vector_rank) if record.vector_rank is not None else None,
                )
                if contribution is not None
            ),
            record,
        )
        for record in records.values()
    ]
    scored.sort(key=lambda item: (-item[0], item[1].chunk.chunk_id))

    return tuple(
        FusedRetrievalCandidate(
            rank=rank,
            rrf_score=score,
            chunk=record.chunk,
            bm25_rank=record.bm25_rank,
            bm25_score=record.bm25_score,
            bm25_highlight=record.bm25_highlight,
            vector_rank=record.vector_rank,
            vector_score=record.vector_score,
        )
        for rank, (score, record) in enumerate(scored[:top_k], start=1)
    )


class HybridRetrievalKernel:
    """Runs mandatory BM25 and degradable Vector recall under one clearance."""

    def __init__(
        self,
        *,
        query_embedding: QueryEmbeddingPort,
        bm25_recall: Bm25RecallPort,
        vector_recall: VectorRecallPort,
        clock: Clock = utc_now,
    ) -> None:
        self._query_embedding = query_embedding
        self._bm25_recall = bm25_recall
        self._vector_recall = vector_recall
        self._context_guard = ExecutionContextGuard(clock)

    async def retrieve(self, request: HybridRetrievalRequest) -> HybridRetrievalResult:
        self._validate_request(request)
        self._validate_clearance(request.context)

        bm25_task = asyncio.create_task(self._run_bm25(request))
        vector_task = asyncio.create_task(self._run_vector(request))
        tasks = (bm25_task, vector_task)
        try:
            bm25_result, vector_branch = await asyncio.gather(*tasks)
        except (asyncio.CancelledError, Exception):
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        self._validate_clearance(request.context)
        vector_result = vector_branch.result
        candidates = reciprocal_rank_fusion(
            bm25_result,
            vector_result,
            k=request.plan.limits.rrf_k,
            top_k=request.plan.limits.fused_top_k,
        )

        return HybridRetrievalResult(
            schema_version="1.0",
            message_execution_id=request.plan.message_execution_id,
            filters=request.plan.filters,
            execution_mode=(
                RetrievalExecutionMode.HYBRID
                if vector_result is not None
                else RetrievalExecutionMode.BM25_ONLY
            ),
            vector_degradation_reason=vector_branch.degradation_reason,
            bm25_provenance=self._provenance(bm25_result),
            vector_provenance=(
                self._provenance(vector_result) if vector_result is not None else None
            ),
            candidates=candidates,
        )

    async def _run_bm25(self, request: HybridRetrievalRequest) -> RecallResult:
        current = self._validate_clearance(request.context)
        context = request.context.context
        recall_request = Bm25RecallRequest(
            normalized_query=request.plan.normalized_query,
            filters=request.plan.filters,
            projection=request.projections.bm25,
            top_k=request.plan.limits.bm25_top_k,
            message_execution_id=context.message_execution_id,
            deadline_at=context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=context.audit,
        )
        try:
            raw_result = await self._bm25_recall.recall(recall_request)
        except Exception as error:
            self._validate_clearance(request.context)
            raise Bm25RecallUnavailable from error

        self._validate_clearance(request.context)
        try:
            result = RecallResult.model_validate(raw_result.model_dump())
            self._validate_recall_result(
                result,
                branch=RecallBranch.BM25,
                plan=request.plan,
                projection=request.projections.bm25,
                embedding_space=None,
            )
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise Bm25RecallContractRejected from error
        return result

    async def _run_vector(self, request: HybridRetrievalRequest) -> _VectorBranchResult:
        current = self._validate_clearance(request.context)
        context = request.context.context
        embedding_request = QueryEmbeddingRequest(
            normalized_query=request.plan.normalized_query,
            locale=request.plan.locale,
            expected_embedding_space_fingerprint=(request.projections.embedding_space_fingerprint),
            message_execution_id=context.message_execution_id,
            deadline_at=context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=context.audit,
        )
        try:
            raw_embedding = await self._query_embedding.embed_query(embedding_request)
        except Exception:
            self._validate_clearance(request.context)
            return _VectorBranchResult(
                result=None,
                degradation_reason=VectorDegradationReason.QUERY_EMBEDDING_UNAVAILABLE,
            )

        current = self._validate_clearance(request.context)
        try:
            embedding = QueryEmbeddingResult.model_validate(raw_embedding.model_dump())
            if (
                embedding.embedding_space_fingerprint
                != request.projections.embedding_space_fingerprint
            ):
                raise ValueError("query embedding used an unexpected vector space")
        except (AttributeError, TypeError, ValueError, ValidationError):
            return _VectorBranchResult(
                result=None,
                degradation_reason=(VectorDegradationReason.QUERY_EMBEDDING_CONTRACT_REJECTED),
            )

        vector_request = VectorRecallRequest(
            query_vector=embedding.vector,
            embedding_space_fingerprint=embedding.embedding_space_fingerprint,
            filters=request.plan.filters,
            projection=request.projections.vector,
            top_k=request.plan.limits.vector_top_k,
            message_execution_id=context.message_execution_id,
            deadline_at=context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=context.audit,
        )
        try:
            raw_result = await self._vector_recall.recall(vector_request)
        except Exception:
            self._validate_clearance(request.context)
            return _VectorBranchResult(
                result=None,
                degradation_reason=VectorDegradationReason.VECTOR_RECALL_UNAVAILABLE,
            )

        self._validate_clearance(request.context)
        try:
            result = RecallResult.model_validate(raw_result.model_dump())
            self._validate_recall_result(
                result,
                branch=RecallBranch.VECTOR,
                plan=request.plan,
                projection=request.projections.vector,
                embedding_space=embedding.embedding_space_fingerprint,
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            return _VectorBranchResult(
                result=None,
                degradation_reason=VectorDegradationReason.VECTOR_CONTRACT_REJECTED,
            )
        return _VectorBranchResult(
            result=result,
            degradation_reason=VectorDegradationReason.NONE,
        )

    def _validate_request(self, request: HybridRetrievalRequest) -> None:
        context = request.context.context
        filters = request.plan.filters
        expected_filter = ProjectRetrievalFilter(
            project_execution_binding_id=context.project_execution_binding_id,
            project_id=context.project_id,
            project_version=context.project_version,
            locale=context.locale,
            access_segment=context.access_segment,
            access_context_hash=context.access_context_hash,
            knowledge_release_id=context.knowledge_release_id,
            revocation_snapshot_version=request.context.revocation_snapshot_version,
            revocation_valid_until=request.context.revocation_valid_until,
            effective_at=request.context.checked_at,
        )
        if (
            request.plan.message_execution_id != context.message_execution_id
            or request.plan.locale != context.locale
            or filters != expected_filter
            or request.projections.knowledge_release_id != context.knowledge_release_id
        ):
            raise RetrievalScopeRejected

    def _validate_clearance(
        self,
        context: RevocationClearedExecutionContext,
    ) -> GuardedExecutionContext:
        current = self._context_guard.validate(context.context)
        if (
            context.revocation_scope != RevocationScope.from_context(context.context)
            or context.revocation_checked_at > current.checked_at
            or context.revocation_valid_until <= current.checked_at
        ):
            raise RevocationStateUnavailable
        return current

    @staticmethod
    def _validate_recall_result(
        result: RecallResult,
        *,
        branch: RecallBranch,
        plan: ProjectQueryPlan,
        projection: RecallProjectionExpectation,
        embedding_space: EmbeddingSpaceFingerprint | None,
    ) -> None:
        top_k = plan.limits.bm25_top_k if branch is RecallBranch.BM25 else plan.limits.vector_top_k
        if (
            result.branch is not branch
            or result.filters != plan.filters
            or result.message_execution_id != plan.message_execution_id
            or result.projection_watermark != projection.projection_watermark
            or result.chunk_manifest_hash != projection.chunk_manifest_hash
            or result.projection_configuration_fingerprint
            != projection.projection_configuration_fingerprint
            or result.embedding_space_fingerprint != embedding_space
            or len(result.hits) > top_k
        ):
            raise ValueError("recall result does not match its trusted request")

    @staticmethod
    def _provenance(result: RecallResult) -> RecallProvenance:
        return RecallProvenance(
            branch=result.branch,
            projection_watermark=result.projection_watermark,
            chunk_manifest_hash=result.chunk_manifest_hash,
            projection_configuration_fingerprint=(result.projection_configuration_fingerprint),
            embedding_space_fingerprint=result.embedding_space_fingerprint,
        )
