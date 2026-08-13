"""Evidence Hub contracts, content revocation checks, and safe citations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, Protocol, Self
from urllib.parse import SplitResult, unquote, urlsplit

from pydantic import Field, ValidationError, field_validator, model_validator

from .execution_context import (
    AccessSegment,
    AuditContext,
    Clock,
    ExecutionContextGuard,
    ExecutionDeadlineExceeded,
    FrozenStrictModel,
    GuardedExecutionContext,
    Identifier,
    LocaleTag,
    utc_now,
)
from .query_planning import (
    ProjectQueryPlan,
    ProjectRetrievalFilter,
    project_retrieval_filter_from_context,
)
from .reranking import (
    RankedRetrievalCandidate,
    RerankerBinding,
    RerankerDegradationReason,
    RerankingMode,
    RerankingResult,
)
from .retrieval import (
    CitationUrl,
    FiniteScore,
    PositiveRank,
    ProjectionText,
    RecallBranch,
    RecallProvenance,
    RetrievalChunk,
    RetrievalExecutionMode,
    Sha256Digest,
    VectorDegradationReason,
)
from .revocation import (
    RevocationClearedExecutionContext,
    RevocationStatus,
    revalidate_cleared_execution_context,
)

EvidenceCount = Annotated[int, Field(ge=0, le=10, strict=True)]
CitationOrigin = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=512, pattern=r"^https://\S+$"),
]


class EvidencePacketStatus(StrEnum):
    READY = "READY"
    EMPTY = "EMPTY"


class CitationKind(StrEnum):
    PUBLIC_HTTPS = "PUBLIC_HTTPS"
    CITATION_PROXY = "CITATION_PROXY"


class CitationPolicy(FrozenStrictModel):
    """Server-owned allowlist for reviewed public citation origins."""

    allowed_https_origins: tuple[CitationOrigin, ...] = ()

    @field_validator("allowed_https_origins", mode="before")
    @classmethod
    def normalize_allowed_origins(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)):
            return value
        return tuple(_canonical_https_origin(origin) for origin in value)

    @model_validator(mode="after")
    def validate_origins(self) -> Self:
        if len(set(self.allowed_https_origins)) != len(self.allowed_https_origins):
            raise ValueError("citation origin allowlist cannot contain duplicates")
        return self


class EvidenceRevocationTarget(FrozenStrictModel):
    """Stable object identities checked against the online content revocation list."""

    chunk_id: Identifier
    document_id: Identifier
    knowledge_revision_id: Identifier
    content_hash: Sha256Digest


class EvidenceRevocationDecision(FrozenStrictModel):
    """Tri-state revocation decision for exactly one candidate target."""

    target: EvidenceRevocationTarget
    status: RevocationStatus


@dataclass(frozen=True, slots=True)
class EvidenceRevocationCheckRequest:
    message_execution_id: str
    filters: ProjectRetrievalFilter
    target_set_fingerprint: str
    targets: tuple[EvidenceRevocationTarget, ...]
    requested_at: datetime
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext


class EvidenceRevocationCheckResult(FrozenStrictModel):
    """Content decisions obtained from one bounded online revocation snapshot."""

    message_execution_id: Identifier
    filters: ProjectRetrievalFilter
    target_set_fingerprint: Sha256Digest
    snapshot_version: Identifier
    checked_at: datetime
    valid_until: datetime
    decisions: tuple[EvidenceRevocationDecision, ...]

    @field_validator("checked_at", "valid_until")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence revocation timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.valid_until <= self.checked_at:
            raise ValueError("evidence revocation validity must end after the check time")
        targets = tuple(decision.target for decision in self.decisions)
        if len(set(targets)) != len(targets):
            raise ValueError("evidence revocation result cannot repeat a target")
        return self


class EvidenceRevocationCheckerPort(Protocol):
    """Checks candidate content against the online emergency revocation view."""

    async def check(
        self,
        request: EvidenceRevocationCheckRequest,
    ) -> EvidenceRevocationCheckResult: ...


class Citation(FrozenStrictModel):
    """Public-safe citation metadata reconstructed from one published chunk."""

    kind: CitationKind
    project_id: Identifier
    project_version: Identifier
    knowledge_space_id: Identifier
    knowledge_release_id: Identifier
    document_id: Identifier
    knowledge_revision_id: Identifier
    locale: LocaleTag
    section: ProjectionText
    citation_url: CitationUrl
    effective_from: datetime | None
    effective_to: datetime | None

    @field_validator("effective_from", "effective_to")
    @classmethod
    def normalize_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("citation effective timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_citation(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("citation effective window must be ordered")
        if _validated_citation_kind(self.citation_url) is not self.kind:
            raise ValueError("citation kind does not match its URL")
        return self


class EvidenceRetrievalProvenance(FrozenStrictModel):
    """Ranks and scores retained for audit, never treated as factual support."""

    rrf_rank: PositiveRank
    rrf_score: FiniteScore
    bm25_rank: PositiveRank | None
    bm25_score: FiniteScore | None
    vector_rank: PositiveRank | None
    vector_score: FiniteScore | None
    reranker_rank: PositiveRank
    reranker_score: FiniteScore | None

    @model_validator(mode="after")
    def validate_branch_fields(self) -> Self:
        bm25_present = self.bm25_rank is not None and self.bm25_score is not None
        vector_present = self.vector_rank is not None and self.vector_score is not None
        if not bm25_present and not vector_present:
            raise ValueError("evidence retrieval must originate from at least one branch")
        if (self.bm25_rank is None) != (self.bm25_score is None):
            raise ValueError("evidence BM25 rank and score must be present together")
        if (self.vector_rank is None) != (self.vector_score is None):
            raise ValueError("evidence vector rank and score must be present together")
        return self


class Evidence(FrozenStrictModel):
    """One content-bearing unit permitted to enter the Prompt Builder."""

    evidence_id: Identifier
    rank: PositiveRank
    chunk_id: Identifier
    content_hash: Sha256Digest
    chunk_manifest_hash: Sha256Digest
    title: ProjectionText
    chunk_text: ProjectionText
    citation: Citation
    retrieval: EvidenceRetrievalProvenance


class EvidencePipelineProvenance(FrozenStrictModel):
    """Retrieval and reranking modes needed for trace and degradation policy."""

    retrieval_execution_mode: RetrievalExecutionMode
    vector_degradation_reason: VectorDegradationReason
    bm25: RecallProvenance
    vector: RecallProvenance | None
    reranking_mode: RerankingMode
    reranker_degradation_reason: RerankerDegradationReason
    reranker_binding: RerankerBinding | None

    @model_validator(mode="after")
    def validate_pipeline(self) -> Self:
        hybrid = self.retrieval_execution_mode is RetrievalExecutionMode.HYBRID
        if hybrid != (self.vector is not None):
            raise ValueError("hybrid evidence provenance requires vector provenance")
        if hybrid != (self.vector_degradation_reason is VectorDegradationReason.NONE):
            raise ValueError("evidence retrieval mode and vector degradation reason disagree")
        if self.bm25.branch is not RecallBranch.BM25:
            raise ValueError("evidence BM25 provenance must identify the BM25 branch")
        if self.bm25.embedding_space_fingerprint is not None:
            raise ValueError("evidence BM25 provenance cannot carry an embedding space")
        if self.vector is not None:
            if self.vector.branch is not RecallBranch.VECTOR:
                raise ValueError("evidence vector provenance must identify the vector branch")
            if self.vector.embedding_space_fingerprint is None:
                raise ValueError("evidence vector provenance requires an embedding space")
            if self.vector.chunk_manifest_hash != self.bm25.chunk_manifest_hash:
                raise ValueError("evidence retrieval provenance must use one chunk manifest")

        reranked = self.reranking_mode is RerankingMode.RERANKER
        fallback = self.reranking_mode is RerankingMode.RRF_FALLBACK
        if reranked and (
            self.reranker_degradation_reason is not RerankerDegradationReason.NONE
            or self.reranker_binding is None
        ):
            raise ValueError("reranker evidence provenance requires a trusted binding")
        if fallback and (
            self.reranker_degradation_reason is RerankerDegradationReason.NONE
            or self.reranker_binding is not None
        ):
            raise ValueError("fallback evidence provenance requires an explicit degradation")
        if (
            not reranked
            and not fallback
            and (
                self.reranker_degradation_reason is not RerankerDegradationReason.NONE
                or self.reranker_binding is not None
            )
        ):
            raise ValueError("empty evidence provenance cannot claim reranker execution")
        return self


class EvidencePacket(FrozenStrictModel):
    """Scope-bound, revocation-checked evidence ready for downstream generation."""

    schema_version: Literal["1.0"]
    status: EvidencePacketStatus
    message_execution_id: Identifier
    project_execution_binding_id: Identifier
    project_id: Identifier
    project_version: Identifier
    locale: LocaleTag
    access_segment: AccessSegment
    access_context_hash: Sha256Digest
    knowledge_release_id: Identifier
    effective_at: datetime
    execution_revocation_snapshot_version: Identifier
    execution_revocation_valid_until: datetime
    content_revocation_snapshot_version: Identifier | None
    content_revocation_valid_until: datetime | None
    input_candidate_count: EvidenceCount
    excluded_revoked_count: EvidenceCount
    pipeline: EvidencePipelineProvenance
    evidence: tuple[Evidence, ...]

    @field_validator(
        "effective_at",
        "execution_revocation_valid_until",
        "content_revocation_valid_until",
    )
    @classmethod
    def normalize_optional_packet_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence packet timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_packet(self) -> Self:
        if (self.status is EvidencePacketStatus.READY) != bool(self.evidence):
            raise ValueError("evidence packet status must reflect whether evidence is present")
        if (self.content_revocation_snapshot_version is None) != (
            self.content_revocation_valid_until is None
        ):
            raise ValueError("content revocation snapshot and validity must be present together")
        if self.input_candidate_count != len(self.evidence) + self.excluded_revoked_count:
            raise ValueError("evidence and revoked counts must cover every input candidate")
        if self.input_candidate_count > 0 and self.content_revocation_snapshot_version is None:
            raise ValueError("non-empty evidence input requires a content revocation snapshot")
        if self.execution_revocation_valid_until <= self.effective_at:
            raise ValueError("execution revocation validity must outlive evidence selection")
        if (
            self.content_revocation_valid_until is not None
            and self.content_revocation_valid_until <= self.effective_at
        ):
            raise ValueError("content revocation validity must outlive evidence selection")
        if (self.input_candidate_count == 0) != (
            self.pipeline.reranking_mode is RerankingMode.EMPTY
        ):
            raise ValueError("empty reranking provenance must match an empty evidence input")
        if tuple(item.rank for item in self.evidence) != tuple(range(1, len(self.evidence) + 1)):
            raise ValueError("evidence ranks must be contiguous and start at one")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("evidence packet cannot repeat an evidence ID")
        if len({item.chunk_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("evidence packet cannot repeat a chunk")
        if len({item.retrieval.rrf_rank for item in self.evidence}) != len(self.evidence):
            raise ValueError("evidence packet cannot repeat an RRF rank")
        if len({item.retrieval.reranker_rank for item in self.evidence}) != len(self.evidence):
            raise ValueError("evidence packet cannot repeat a reranker rank")
        for item in self.evidence:
            if (
                item.evidence_id
                != _evidence_identity(
                    self.message_execution_id,
                    item.chunk_id,
                    item.citation.knowledge_revision_id,
                    item.content_hash,
                )
                or item.chunk_manifest_hash != self.pipeline.bm25.chunk_manifest_hash
                or item.citation.project_id != self.project_id
                or item.citation.project_version != self.project_version
                or item.citation.knowledge_release_id != self.knowledge_release_id
                or item.citation.locale != self.locale
            ):
                raise ValueError("evidence item does not match the packet scope")
            if (
                item.citation.effective_from is not None
                and self.effective_at < item.citation.effective_from
            ):
                raise ValueError("evidence item is not effective yet")
            if (
                item.citation.effective_to is not None
                and self.effective_at >= item.citation.effective_to
            ):
                raise ValueError("evidence item is no longer effective")
            if (
                self.pipeline.retrieval_execution_mode is RetrievalExecutionMode.BM25_ONLY
                and item.retrieval.vector_rank is not None
            ):
                raise ValueError("BM25-only evidence cannot carry vector provenance")
            if self.pipeline.reranking_mode is RerankingMode.RERANKER:
                if item.retrieval.reranker_score is None:
                    raise ValueError("reranked evidence requires a reranker score")
            elif item.retrieval.reranker_score is not None:
                raise ValueError("non-reranked evidence cannot carry a reranker score")
        return self


class EvidenceRejected(RuntimeError):
    code = "evidence_rejected"


class EvidenceScopeRejected(EvidenceRejected):
    code = "evidence_scope_rejected"


class EvidenceRevocationStateUnavailable(EvidenceRejected):
    code = "evidence_revocation_state_unavailable"


class EvidenceCitationRejected(EvidenceRejected):
    code = "evidence_citation_rejected"


@dataclass(frozen=True, slots=True)
class EvidenceHubRequest:
    context: RevocationClearedExecutionContext
    plan: ProjectQueryPlan
    reranking: RerankingResult
    citation_policy: CitationPolicy


class EvidenceHub:
    """Reapplies domain boundaries and excludes known-revoked candidate content."""

    def __init__(
        self,
        revocation_checker: EvidenceRevocationCheckerPort,
        *,
        max_revocation_ttl: timedelta,
        clock: Clock = utc_now,
    ) -> None:
        if max_revocation_ttl <= timedelta(0):
            raise ValueError("evidence revocation TTL must be positive")
        self._revocation_checker = revocation_checker
        self._max_revocation_ttl = max_revocation_ttl
        self._context_guard = ExecutionContextGuard(clock)

    async def build(self, request: EvidenceHubRequest) -> EvidencePacket:
        current, request = self._validate_request(request)
        reranking = request.reranking
        if not reranking.candidates:
            return self._packet(
                request,
                reranking,
                content_snapshot_version=None,
                content_valid_until=None,
                excluded_revoked_count=0,
                evidence=(),
            )

        targets = tuple(
            _revocation_target(candidate.candidate.chunk) for candidate in reranking.candidates
        )
        context = request.context.context
        check_request = EvidenceRevocationCheckRequest(
            message_execution_id=context.message_execution_id,
            filters=request.plan.filters,
            target_set_fingerprint=_target_set_fingerprint(targets),
            targets=targets,
            requested_at=current.checked_at,
            deadline_at=context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=context.audit,
        )
        try:
            async with asyncio.timeout(check_request.deadline_remaining.total_seconds()):
                raw_result = await self._revocation_checker.check(check_request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except Exception as error:
            self._validate_context(request.context)
            raise EvidenceRevocationStateUnavailable from error

        current = self._validate_context(request.context)
        try:
            result = EvidenceRevocationCheckResult.model_validate(raw_result.model_dump())
            self._validate_revocation_result(result, check_request, current)
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise EvidenceRevocationStateUnavailable from error

        if any(decision.status is RevocationStatus.UNKNOWN for decision in result.decisions):
            raise EvidenceRevocationStateUnavailable

        decisions = {decision.target: decision.status for decision in result.decisions}
        clear_candidates = tuple(
            candidate
            for candidate, target in zip(reranking.candidates, targets, strict=True)
            if decisions[target] is RevocationStatus.CLEAR
        )
        evidence = tuple(
            self._evidence(
                context.message_execution_id,
                rank,
                candidate,
                request.citation_policy.allowed_https_origins,
            )
            for rank, candidate in enumerate(clear_candidates, start=1)
        )
        return self._packet(
            request,
            reranking,
            content_snapshot_version=result.snapshot_version,
            content_valid_until=result.valid_until,
            excluded_revoked_count=len(reranking.candidates) - len(clear_candidates),
            evidence=evidence,
        )

    def _validate_request(
        self,
        request: EvidenceHubRequest,
    ) -> tuple[GuardedExecutionContext, EvidenceHubRequest]:
        current = self._validate_context(request.context)
        try:
            plan = ProjectQueryPlan.model_validate(request.plan.model_dump())
            reranking = RerankingResult.model_validate(request.reranking.model_dump())
            citation_policy = CitationPolicy.model_validate(request.citation_policy.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise EvidenceScopeRejected from error
        context = request.context.context
        if (
            plan.message_execution_id != context.message_execution_id
            or plan.filters != project_retrieval_filter_from_context(request.context)
            or reranking.message_execution_id != plan.message_execution_id
            or reranking.filters != plan.filters
        ):
            raise EvidenceScopeRejected
        return current, EvidenceHubRequest(
            context=request.context,
            plan=plan,
            reranking=reranking,
            citation_policy=citation_policy,
        )

    def _validate_context(
        self,
        context: RevocationClearedExecutionContext,
    ) -> GuardedExecutionContext:
        return revalidate_cleared_execution_context(context, self._context_guard)

    def _validate_revocation_result(
        self,
        result: EvidenceRevocationCheckResult,
        request: EvidenceRevocationCheckRequest,
        current: GuardedExecutionContext,
    ) -> None:
        if (
            result.message_execution_id != request.message_execution_id
            or result.filters != request.filters
            or result.target_set_fingerprint != request.target_set_fingerprint
            or tuple(decision.target for decision in result.decisions) != request.targets
            or result.checked_at > current.checked_at
            or result.valid_until <= current.checked_at
            or result.valid_until - result.checked_at > self._max_revocation_ttl
        ):
            raise ValueError("evidence revocation result does not match the trusted request")

    @staticmethod
    def _evidence(
        message_execution_id: str,
        rank: int,
        candidate: RankedRetrievalCandidate,
        allowed_citation_origins: tuple[str, ...],
    ) -> Evidence:
        chunk = candidate.candidate.chunk
        citation = _citation(chunk, allowed_citation_origins)
        return Evidence(
            evidence_id=_evidence_id(message_execution_id, chunk),
            rank=rank,
            chunk_id=chunk.chunk_id,
            content_hash=chunk.content_hash,
            chunk_manifest_hash=chunk.chunk_manifest_hash,
            title=chunk.title,
            chunk_text=chunk.chunk_text,
            citation=citation,
            retrieval=EvidenceRetrievalProvenance(
                rrf_rank=candidate.candidate.rank,
                rrf_score=candidate.candidate.rrf_score,
                bm25_rank=candidate.candidate.bm25_rank,
                bm25_score=candidate.candidate.bm25_score,
                vector_rank=candidate.candidate.vector_rank,
                vector_score=candidate.candidate.vector_score,
                reranker_rank=candidate.rank,
                reranker_score=candidate.reranker_score,
            ),
        )

    @staticmethod
    def _packet(
        request: EvidenceHubRequest,
        reranking: RerankingResult,
        *,
        content_snapshot_version: str | None,
        content_valid_until: datetime | None,
        excluded_revoked_count: int,
        evidence: tuple[Evidence, ...],
    ) -> EvidencePacket:
        filters = reranking.filters
        return EvidencePacket(
            schema_version="1.0",
            status=(EvidencePacketStatus.READY if evidence else EvidencePacketStatus.EMPTY),
            message_execution_id=reranking.message_execution_id,
            project_execution_binding_id=filters.project_execution_binding_id,
            project_id=filters.project_id,
            project_version=filters.project_version,
            locale=filters.locale,
            access_segment=filters.access_segment,
            access_context_hash=filters.access_context_hash,
            knowledge_release_id=filters.knowledge_release_id,
            effective_at=filters.effective_at,
            execution_revocation_snapshot_version=filters.revocation_snapshot_version,
            execution_revocation_valid_until=filters.revocation_valid_until,
            content_revocation_snapshot_version=content_snapshot_version,
            content_revocation_valid_until=content_valid_until,
            input_candidate_count=len(reranking.candidates),
            excluded_revoked_count=excluded_revoked_count,
            pipeline=EvidencePipelineProvenance(
                retrieval_execution_mode=reranking.retrieval_execution_mode,
                vector_degradation_reason=reranking.vector_degradation_reason,
                bm25=reranking.bm25_provenance,
                vector=reranking.vector_provenance,
                reranking_mode=reranking.mode,
                reranker_degradation_reason=reranking.degradation_reason,
                reranker_binding=reranking.binding,
            ),
            evidence=evidence,
        )


def _revocation_target(chunk: RetrievalChunk) -> EvidenceRevocationTarget:
    return EvidenceRevocationTarget(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        knowledge_revision_id=chunk.knowledge_revision_id,
        content_hash=chunk.content_hash,
    )


def _target_set_fingerprint(targets: tuple[EvidenceRevocationTarget, ...]) -> str:
    payload = "\n".join(
        "\x1f".join(
            (
                target.chunk_id,
                target.document_id,
                target.knowledge_revision_id,
                target.content_hash,
            )
        )
        for target in targets
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _evidence_id(message_execution_id: str, chunk: RetrievalChunk) -> str:
    return _evidence_identity(
        message_execution_id,
        chunk.chunk_id,
        chunk.knowledge_revision_id,
        chunk.content_hash,
    )


def _evidence_identity(
    message_execution_id: str,
    chunk_id: str,
    knowledge_revision_id: str,
    content_hash: str,
) -> str:
    payload = "\x1f".join((message_execution_id, chunk_id, knowledge_revision_id, content_hash))
    return f"evidence-{sha256(payload.encode('utf-8')).hexdigest()}"


def _validated_citation_kind(
    citation_url: str,
    allowed_origins: tuple[str, ...] | None = None,
) -> CitationKind:
    try:
        parsed = urlsplit(citation_url)
        _ = parsed.port
    except ValueError as error:
        raise EvidenceCitationRejected from error

    decoded_path = parsed.path
    while True:
        if (
            "\\" in decoded_path
            or ".." in decoded_path.split("/")
            or decoded_path.startswith("//")
            or any(ord(character) < 32 or ord(character) == 127 for character in decoded_path)
        ):
            raise EvidenceCitationRejected
        next_path = unquote(decoded_path)
        if next_path == decoded_path:
            break
        decoded_path = next_path

    if parsed.scheme == "https":
        try:
            origin = _canonical_https_origin_from_parts(parsed, require_empty_components=False)
        except ValueError as error:
            raise EvidenceCitationRejected from error
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or (allowed_origins is not None and origin not in allowed_origins)
        ):
            raise EvidenceCitationRejected
        return CitationKind.PUBLIC_HTTPS
    if (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path.startswith("/")
        and not parsed.path.startswith("//")
    ):
        return CitationKind.CITATION_PROXY
    raise EvidenceCitationRejected


def _canonical_https_origin(origin: object) -> str:
    if not isinstance(origin, str):
        raise ValueError("citation origin must be a valid HTTPS origin")
    try:
        parsed = urlsplit(origin)
        canonical = _canonical_https_origin_from_parts(parsed)
        host = parsed.hostname
        assert host is not None
        normalized_host = host.lower()
        if ":" in normalized_host and not normalized_host.startswith("["):
            normalized_host = f"[{normalized_host}]"
        raw_authority = (
            normalized_host if parsed.port is None else f"{normalized_host}:{parsed.port}"
        )
        if origin != f"https://{raw_authority}":
            raise ValueError("citation origin must be a canonical HTTPS origin")
        return canonical
    except (TypeError, ValueError) as error:
        raise ValueError("citation origin must be a valid HTTPS origin") from error


def _canonical_https_origin_from_parts(
    parsed: SplitResult,
    *,
    require_empty_components: bool = True,
) -> str:
    try:
        scheme = parsed.scheme
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as error:
        raise ValueError("citation origin must be a valid HTTPS origin") from error
    if (
        scheme != "https"
        or not hostname
        or username is not None
        or password is not None
        or (require_empty_components and (parsed.path or parsed.query or parsed.fragment))
    ):
        raise ValueError("citation origin must be a canonical HTTPS origin")
    host = hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    authority = host if port in (None, 443) else f"{host}:{port}"
    return f"https://{authority}"


def _citation(chunk: RetrievalChunk, allowed_origins: tuple[str, ...]) -> Citation:
    kind = _validated_citation_kind(chunk.citation_url, allowed_origins)

    return Citation(
        kind=kind,
        project_id=chunk.project_id,
        project_version=chunk.project_version,
        knowledge_space_id=chunk.knowledge_space_id,
        knowledge_release_id=chunk.knowledge_release_id,
        document_id=chunk.document_id,
        knowledge_revision_id=chunk.knowledge_revision_id,
        locale=chunk.locale,
        section=chunk.section,
        citation_url=chunk.citation_url,
        effective_from=chunk.effective_from,
        effective_to=chunk.effective_to,
    )
