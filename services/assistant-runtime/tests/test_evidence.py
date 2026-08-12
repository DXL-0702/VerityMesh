import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from support.retrieval import (
    MANIFEST_HASH,
    MutableClock,
    ScriptedEvidenceRevocationChecker,
    chunk,
    retrieval_request,
)
from veritymesh_assistant_runtime.evidence import (
    Citation,
    CitationKind,
    CitationPolicy,
    Evidence,
    EvidenceCitationRejected,
    EvidenceHub,
    EvidenceHubRequest,
    EvidencePacket,
    EvidencePacketStatus,
    EvidencePipelineProvenance,
    EvidenceRetrievalProvenance,
    EvidenceRevocationCheckerPort,
    EvidenceRevocationCheckRequest,
    EvidenceRevocationCheckResult,
    EvidenceRevocationDecision,
    EvidenceRevocationStateUnavailable,
    EvidenceScopeRejected,
)
from veritymesh_assistant_runtime.execution_context import (
    AccessSegment,
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.reranking import (
    RankedRetrievalCandidate,
    RerankerBinding,
    RerankerDegradationReason,
    RerankingMode,
    RerankingResult,
)
from veritymesh_assistant_runtime.retrieval import (
    FusedRetrievalCandidate,
    RecallBranch,
    RecallProvenance,
    RetrievalExecutionMode,
    VectorDegradationReason,
)
from veritymesh_assistant_runtime.revocation import RevocationStatus

MAX_REVOCATION_TTL = timedelta(seconds=30)
RERANKER_CONFIGURATION = "6" * 64


def binding() -> RerankerBinding:
    return RerankerBinding(
        logical_model="reranker-primary",
        provider="aliyun-bailian",
        region="cn-beijing",
        api_mode="native",
        model="qwen3-rerank",
        revision="rerank-revision-1",
        configuration_fingerprint=RERANKER_CONFIGURATION,
    )


def fused_candidate(
    rank: int,
    chunk_id: str,
    *,
    citation_url: str | None = None,
    reranker_score: float | None = 0.9,
) -> RankedRetrievalCandidate:
    return RankedRetrievalCandidate(
        rank=rank,
        candidate=FusedRetrievalCandidate(
            rank=rank,
            rrf_score=1 / (60 + rank),
            chunk=chunk(chunk_id, citation_url=citation_url),
            bm25_rank=rank,
            bm25_score=10.0 - rank,
            bm25_highlight=None,
            vector_rank=None,
            vector_score=None,
        ),
        reranker_score=reranker_score,
    )


def reranking(
    context_factory: Callable[..., ProjectExecutionContext],
    *candidates: RankedRetrievalCandidate,
    mode: RerankingMode = RerankingMode.RERANKER,
) -> tuple[EvidenceHubRequest, RerankingResult]:
    retrieval = retrieval_request(context_factory)
    if mode is RerankingMode.RERANKER:
        degradation_reason = RerankerDegradationReason.NONE
        reranker_binding: RerankerBinding | None = binding()
    elif mode is RerankingMode.RRF_FALLBACK:
        degradation_reason = RerankerDegradationReason.RERANKER_UNAVAILABLE
        reranker_binding = None
    else:
        degradation_reason = RerankerDegradationReason.NONE
        reranker_binding = None

    result = RerankingResult(
        schema_version="1.0",
        message_execution_id=retrieval.plan.message_execution_id,
        filters=retrieval.plan.filters,
        retrieval_execution_mode=RetrievalExecutionMode.HYBRID,
        vector_degradation_reason=VectorDegradationReason.NONE,
        bm25_provenance=RecallProvenance(
            branch=RecallBranch.BM25,
            projection_watermark="bm25-watermark-1",
            chunk_manifest_hash=MANIFEST_HASH,
            projection_configuration_fingerprint="2" * 64,
            embedding_space_fingerprint=None,
        ),
        vector_provenance=RecallProvenance(
            branch=RecallBranch.VECTOR,
            projection_watermark="vector-watermark-1",
            chunk_manifest_hash=MANIFEST_HASH,
            projection_configuration_fingerprint="3" * 64,
            embedding_space_fingerprint=retrieval.projections.embedding_space_fingerprint,
        ),
        mode=mode,
        degradation_reason=degradation_reason,
        binding=reranker_binding,
        candidates=candidates,
    )
    return (
        EvidenceHubRequest(
            context=retrieval.context,
            plan=retrieval.plan,
            reranking=result,
            citation_policy=CitationPolicy(),
        ),
        result,
    )


def evidence_hub(
    checker: EvidenceRevocationCheckerPort,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
) -> EvidenceHub:
    return EvidenceHub(
        checker,
        max_revocation_ttl=MAX_REVOCATION_TTL,
        clock=clock,
    )


def revocation_result(
    request: EvidenceRevocationCheckRequest,
    *statuses: RevocationStatus,
    checked_at: datetime = NOW,
    valid_until: datetime = NOW + timedelta(seconds=10),
) -> EvidenceRevocationCheckResult:
    return EvidenceRevocationCheckResult(
        message_execution_id=request.message_execution_id,
        filters=request.filters,
        target_set_fingerprint=request.target_set_fingerprint,
        snapshot_version="content-revocation-snapshot-3",
        checked_at=checked_at,
        valid_until=valid_until,
        decisions=tuple(
            EvidenceRevocationDecision(target=target, status=status)
            for target, status in zip(request.targets, statuses, strict=True)
        ),
    )


class RespondingEvidenceRevocationChecker:
    def __init__(
        self,
        response: Callable[[EvidenceRevocationCheckRequest], EvidenceRevocationCheckResult],
    ) -> None:
        self._response = response
        self.requests: list[EvidenceRevocationCheckRequest] = []

    async def check(
        self,
        request: EvidenceRevocationCheckRequest,
    ) -> EvidenceRevocationCheckResult:
        self.requests.append(request)
        return self._response(request)


def test_clear_candidates_produce_a_scope_bound_evidence_packet(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, result = reranking(
        context_factory,
        fused_candidate(1, "a"),
        fused_candidate(2, "b"),
    )
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(
            check_request,
            RevocationStatus.CLEAR,
            RevocationStatus.CLEAR,
        )
    )

    packet = asyncio.run(evidence_hub(checker).build(request))

    assert packet.status is EvidencePacketStatus.READY
    assert packet.message_execution_id == result.message_execution_id
    assert packet.project_id == "project-1"
    assert packet.access_segment is AccessSegment.PROJECT_AUTHORIZED
    assert packet.input_candidate_count == 2
    assert packet.excluded_revoked_count == 0
    assert packet.content_revocation_snapshot_version == "content-revocation-snapshot-3"
    assert packet.content_revocation_valid_until == NOW + timedelta(seconds=10)
    assert [item.rank for item in packet.evidence] == [1, 2]
    assert [item.chunk_id for item in packet.evidence] == ["a", "b"]
    assert packet.evidence[0].citation.kind is CitationKind.CITATION_PROXY
    assert packet.evidence[0].retrieval.rrf_rank == 1
    assert packet.evidence[0].retrieval.reranker_rank == 1
    assert packet.evidence[0].retrieval.reranker_score == 0.9
    assert checker.requests[0].filters == request.plan.filters
    assert checker.requests[0].targets[0].chunk_id == "a"


def test_revoked_candidate_is_excluded_and_remaining_evidence_is_renumbered(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(
        context_factory,
        fused_candidate(1, "a"),
        fused_candidate(2, "b"),
    )
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(
            check_request,
            RevocationStatus.REVOKED,
            RevocationStatus.CLEAR,
        )
    )

    packet = asyncio.run(evidence_hub(checker).build(request))

    assert packet.status is EvidencePacketStatus.READY
    assert packet.excluded_revoked_count == 1
    assert [(item.rank, item.chunk_id) for item in packet.evidence] == [(1, "b")]
    assert packet.evidence[0].retrieval.rrf_rank == 2
    assert packet.evidence[0].retrieval.reranker_rank == 2


def test_all_revoked_candidates_produce_an_empty_packet_with_the_content_snapshot(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.REVOKED)
    )

    packet = asyncio.run(evidence_hub(checker).build(request))

    assert packet.status is EvidencePacketStatus.EMPTY
    assert packet.evidence == ()
    assert packet.input_candidate_count == 1
    assert packet.excluded_revoked_count == 1
    assert packet.content_revocation_snapshot_version == "content-revocation-snapshot-3"


def test_empty_reranking_skips_content_revocation(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, mode=RerankingMode.EMPTY)
    checker = ScriptedEvidenceRevocationChecker([])

    packet = asyncio.run(evidence_hub(checker).build(request))

    assert packet.status is EvidencePacketStatus.EMPTY
    assert packet.content_revocation_snapshot_version is None
    assert packet.content_revocation_valid_until is None
    assert checker.requests == []


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "execution",
        "filters",
        "fingerprint",
        "order",
        "missing",
        "extra",
        "duplicate",
        "future",
        "expired",
        "oversized_ttl",
    ],
)
def test_unknown_or_invalid_content_revocation_results_fail_closed(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
) -> None:
    request, _ = reranking(
        context_factory,
        fused_candidate(1, "a"),
        fused_candidate(2, "b"),
    )

    def response(check_request: EvidenceRevocationCheckRequest) -> EvidenceRevocationCheckResult:
        if mutation == "unknown":
            return revocation_result(
                check_request,
                RevocationStatus.CLEAR,
                RevocationStatus.UNKNOWN,
            )
        result = revocation_result(
            check_request,
            RevocationStatus.CLEAR,
            RevocationStatus.CLEAR,
        )
        values = result.model_dump()
        if mutation == "execution":
            values["message_execution_id"] = "other-execution"
        elif mutation == "filters":
            cast(dict[str, object], values["filters"])["project_id"] = "other-project"
        elif mutation == "fingerprint":
            values["target_set_fingerprint"] = "9" * 64
        elif mutation == "order":
            cast(list[object], values["decisions"]).reverse()
        elif mutation == "missing":
            values["decisions"] = cast(list[object], values["decisions"])[:1]
        elif mutation == "extra":
            decisions = cast(list[dict[str, object]], values["decisions"])
            extra_target = dict(cast(dict[str, object], decisions[0]["target"]))
            extra_target["chunk_id"] = "extra"
            extra_target["document_id"] = "document-extra"
            extra_target["knowledge_revision_id"] = "revision-extra"
            decisions.append({"target": extra_target, "status": "CLEAR"})
        elif mutation == "duplicate":
            decisions = cast(list[dict[str, object]], values["decisions"])
            decisions[1]["target"] = decisions[0]["target"]
        elif mutation == "future":
            values["checked_at"] = NOW + timedelta(seconds=1)
            values["valid_until"] = NOW + timedelta(seconds=2)
        elif mutation == "expired":
            values["checked_at"] = NOW - timedelta(seconds=2)
            values["valid_until"] = NOW
        else:
            values["valid_until"] = NOW + MAX_REVOCATION_TTL + timedelta(seconds=1)
        return EvidenceRevocationCheckResult.model_validate(values)

    with pytest.raises(EvidenceRevocationStateUnavailable):
        asyncio.run(evidence_hub(RespondingEvidenceRevocationChecker(response)).build(request))


def test_content_revocation_failure_and_cancellation_are_not_misclassified(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    failure = RuntimeError("content revocation unavailable")

    with pytest.raises(EvidenceRevocationStateUnavailable) as raised:
        asyncio.run(evidence_hub(ScriptedEvidenceRevocationChecker([failure])).build(request))
    assert raised.value.__cause__ is failure

    class CancelledChecker:
        async def check(
            self,
            _request: EvidenceRevocationCheckRequest,
        ) -> EvidenceRevocationCheckResult:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(evidence_hub(CancelledChecker()).build(request))


def test_content_revocation_provider_timeout_is_mapped_to_unavailable(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))

    class TimeoutChecker:
        async def check(
            self,
            _request: EvidenceRevocationCheckRequest,
        ) -> EvidenceRevocationCheckResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout content checker unexpectedly returned")

    with pytest.raises(EvidenceRevocationStateUnavailable):
        asyncio.run(evidence_hub(TimeoutChecker()).build(request))


def test_content_revocation_provider_deadline_error_propagates(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))

    class DeadlineChecker:
        async def check(
            self,
            _request: EvidenceRevocationCheckRequest,
        ) -> EvidenceRevocationCheckResult:
            raise ExecutionDeadlineExceeded

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(evidence_hub(DeadlineChecker()).build(request))


def test_deadline_prevents_or_takes_precedence_after_content_revocation(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    expired = evidence_hub(
        ScriptedEvidenceRevocationChecker([]),
        clock=lambda: NOW + timedelta(seconds=3),
    )

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(expired.build(request))

    clock = MutableClock(NOW)

    class LateFailure:
        async def check(
            self,
            _request: EvidenceRevocationCheckRequest,
        ) -> EvidenceRevocationCheckResult:
            clock.current = NOW + timedelta(seconds=3)
            raise RuntimeError("late failure")

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(evidence_hub(LateFailure(), clock=clock).build(request))


@pytest.mark.parametrize(
    "mutation",
    [
        "plan_execution",
        "plan_filter",
        "reranking_execution",
        "reranking_filter",
        "reranking_chunk_scope",
        "reranking_manifest",
        "reranking_effective_window",
        "citation_policy",
    ],
)
def test_invalid_evidence_inputs_prevent_content_revocation_calls(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    if mutation == "plan_execution":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan.model_copy(update={"message_execution_id": "other-execution"}),
            reranking=request.reranking,
            citation_policy=request.citation_policy,
        )
    elif mutation == "plan_filter":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan.model_copy(
                update={"filters": request.plan.filters.model_copy(update={"project_id": "other"})}
            ),
            reranking=request.reranking,
            citation_policy=request.citation_policy,
        )
    elif mutation == "reranking_execution":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan,
            reranking=request.reranking.model_copy(
                update={"message_execution_id": "other-execution"}
            ),
            citation_policy=request.citation_policy,
        )
    elif mutation == "reranking_filter":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan,
            reranking=request.reranking.model_copy(
                update={
                    "filters": request.reranking.filters.model_copy(update={"project_id": "other"})
                }
            ),
            citation_policy=request.citation_policy,
        )
    elif mutation == "reranking_chunk_scope":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan,
            reranking=request.reranking.model_copy(
                update={
                    "candidates": (
                        request.reranking.candidates[0].model_copy(
                            update={
                                "candidate": request.reranking.candidates[0].candidate.model_copy(
                                    update={
                                        "chunk": request.reranking.candidates[
                                            0
                                        ].candidate.chunk.model_copy(
                                            update={"access_segment": AccessSegment.PUBLIC}
                                        )
                                    }
                                )
                            }
                        ),
                    )
                }
            ),
            citation_policy=request.citation_policy,
        )
    elif mutation == "reranking_manifest":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan,
            reranking=request.reranking.model_copy(
                update={
                    "candidates": (
                        request.reranking.candidates[0].model_copy(
                            update={
                                "candidate": request.reranking.candidates[0].candidate.model_copy(
                                    update={
                                        "chunk": request.reranking.candidates[
                                            0
                                        ].candidate.chunk.model_copy(
                                            update={"chunk_manifest_hash": "9" * 64}
                                        )
                                    }
                                )
                            }
                        ),
                    )
                }
            ),
            citation_policy=request.citation_policy,
        )
    elif mutation == "reranking_effective_window":
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan,
            reranking=request.reranking.model_copy(
                update={
                    "candidates": (
                        request.reranking.candidates[0].model_copy(
                            update={
                                "candidate": request.reranking.candidates[0].candidate.model_copy(
                                    update={
                                        "chunk": request.reranking.candidates[
                                            0
                                        ].candidate.chunk.model_copy(update={"effective_to": NOW})
                                    }
                                )
                            }
                        ),
                    )
                }
            ),
            citation_policy=request.citation_policy,
        )
    else:
        invalid = EvidenceHubRequest(
            context=request.context,
            plan=request.plan,
            reranking=request.reranking,
            citation_policy=request.citation_policy.model_copy(
                update={"allowed_https_origins": ("https://docs.example.com/path",)}
            ),
        )
    checker = ScriptedEvidenceRevocationChecker([])

    with pytest.raises(EvidenceScopeRejected):
        asyncio.run(evidence_hub(checker).build(invalid))
    assert checker.requests == []


def test_proxy_and_allowlisted_https_citations_are_safe(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    proxy_request, _ = reranking(context_factory, fused_candidate(1, "proxy"))
    proxy_checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    proxy_packet = asyncio.run(evidence_hub(proxy_checker).build(proxy_request))

    https_request, _ = reranking(
        context_factory,
        fused_candidate(1, "public", citation_url="https://docs.example.com/guide/api"),
    )
    https_request = EvidenceHubRequest(
        context=https_request.context,
        plan=https_request.plan,
        reranking=https_request.reranking,
        citation_policy=CitationPolicy(allowed_https_origins=("https://docs.example.com",)),
    )
    https_checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    https_packet = asyncio.run(evidence_hub(https_checker).build(https_request))

    assert proxy_packet.evidence[0].citation.kind is CitationKind.CITATION_PROXY
    assert https_packet.evidence[0].citation.kind is CitationKind.PUBLIC_HTTPS
    assert https_packet.evidence[0].citation.citation_url == "https://docs.example.com/guide/api"


@pytest.mark.parametrize(
    "citation_url",
    [
        "http://docs.example.com/guide",
        "https://untrusted.example.com/guide",
        "https://user:password@docs.example.com/guide",
        "https://docs.example.com:bad/guide",
        "//docs.example.com/guide",
        "file:///private/source.md",
        "/citations/../private",
        "/citations/%2e%2e/private",
        "/citations/%252e%252e/private",
        "/citations\\private",
    ],
)
def test_unsafe_citation_urls_are_rejected_after_clear_revocation(
    context_factory: Callable[..., ProjectExecutionContext],
    citation_url: str,
) -> None:
    request, _ = reranking(
        context_factory,
        fused_candidate(1, "a", citation_url=citation_url),
    )
    request = EvidenceHubRequest(
        context=request.context,
        plan=request.plan,
        reranking=request.reranking,
        citation_policy=CitationPolicy(allowed_https_origins=("https://docs.example.com",)),
    )
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )

    with pytest.raises(EvidenceCitationRejected):
        asyncio.run(evidence_hub(checker).build(request))


@pytest.mark.parametrize(
    "origin",
    [
        "https://docs.example.com",
        "https://docs.example.com:443",
    ],
)
def test_citation_policy_accepts_canonical_https_origins(origin: str) -> None:
    assert CitationPolicy(allowed_https_origins=(origin,)).allowed_https_origins == (
        "https://docs.example.com",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "https://docs.example.com/",
        "https://Docs.Example.com",
        "https://docs.example.com/path",
        "https://docs.example.com?query=1",
        "https://docs.example.com#fragment",
        "https://user@docs.example.com",
        "http://docs.example.com",
        "https://docs.example.com:bad",
    ],
)
def test_citation_policy_rejects_noncanonical_or_unsafe_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        CitationPolicy(allowed_https_origins=(origin,))


def test_citation_policy_rejects_duplicate_origins() -> None:
    with pytest.raises(ValidationError, match="cannot contain duplicates"):
        CitationPolicy(
            allowed_https_origins=("https://docs.example.com", "https://docs.example.com")
        )


def test_citation_policy_rejects_non_string_origins() -> None:
    with pytest.raises(ValidationError):
        CitationPolicy.model_validate({"allowed_https_origins": (123,)})


def test_citation_policy_normalizes_default_https_port() -> None:
    policy = CitationPolicy(allowed_https_origins=("https://docs.example.com:443",))
    assert policy.allowed_https_origins == ("https://docs.example.com",)


def test_citation_policy_normalizes_ipv6_origin() -> None:
    policy = CitationPolicy(allowed_https_origins=("https://[2001:db8::1]:443",))
    assert policy.allowed_https_origins == ("https://[2001:db8::1]",)


def test_citation_policy_rejects_non_sequence_input() -> None:
    with pytest.raises(ValidationError):
        CitationPolicy.model_validate({"allowed_https_origins": "https://docs.example.com"})


def test_citation_policy_rejects_duplicate_after_origin_normalization() -> None:
    with pytest.raises(ValidationError, match="cannot contain duplicates"):
        CitationPolicy(
            allowed_https_origins=("https://docs.example.com", "https://docs.example.com:443")
        )


def test_evidence_packet_rejects_inconsistent_state_and_deterministically_binds_ids(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    packet = asyncio.run(evidence_hub(checker).build(request))
    duplicate_execution = EvidencePacket.model_validate(packet.model_dump())

    assert duplicate_execution.evidence[0].evidence_id == packet.evidence[0].evidence_id
    values = packet.model_dump()
    values["message_execution_id"] = "another-execution"
    with pytest.raises(ValidationError, match="evidence item does not match"):
        EvidencePacket.model_validate(values)

    values = packet.model_dump()
    cast(list[dict[str, object]], values["evidence"])[0]["rank"] = 2
    with pytest.raises(ValidationError, match="evidence ranks"):
        EvidencePacket.model_validate(values)

    values = packet.model_dump()
    values["content_revocation_valid_until"] = None
    with pytest.raises(ValidationError, match="present together"):
        EvidencePacket.model_validate(values)


def test_evidence_model_contracts_reject_bad_shapes(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    packet = asyncio.run(evidence_hub(checker).build(request))

    citation_values = packet.evidence[0].citation.model_dump()
    citation_values["kind"] = CitationKind.PUBLIC_HTTPS
    with pytest.raises(ValidationError, match="kind does not match"):
        Citation.model_validate(citation_values)

    retrieval_values = packet.evidence[0].retrieval.model_dump()
    retrieval_values["bm25_score"] = None
    with pytest.raises(ValidationError, match="at least one branch"):
        EvidenceRetrievalProvenance.model_validate(retrieval_values)

    evidence_values = packet.evidence[0].model_dump()
    evidence_values["evidence_id"] = "other-evidence"
    invalid_evidence = Evidence.model_validate(evidence_values)
    packet_values = packet.model_dump()
    packet_values["evidence"] = [invalid_evidence.model_dump()]
    with pytest.raises(ValidationError, match="evidence item does not match"):
        EvidencePacket.model_validate(packet_values)


def test_revocation_and_citation_contracts_require_valid_time_windows(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    packet = asyncio.run(evidence_hub(checker).build(request))

    revocation_values = revocation_result(
        checker.requests[0],
        RevocationStatus.CLEAR,
    ).model_dump()
    revocation_values["checked_at"] = datetime(2026, 8, 11, 8, 0)
    with pytest.raises(ValidationError, match="must include a timezone"):
        EvidenceRevocationCheckResult.model_validate(revocation_values)

    revocation_values["checked_at"] = NOW
    revocation_values["valid_until"] = NOW
    with pytest.raises(ValidationError, match="must end after"):
        EvidenceRevocationCheckResult.model_validate(revocation_values)

    citation_values = packet.evidence[0].citation.model_dump()
    citation_values["effective_from"] = None
    citation_values["effective_to"] = None
    citation = Citation.model_validate(citation_values)
    assert citation.effective_from is None

    citation_values["effective_from"] = datetime(2026, 8, 11, 8, 0)
    with pytest.raises(ValidationError, match="must include a timezone"):
        Citation.model_validate(citation_values)

    citation_values["effective_from"] = NOW
    citation_values["effective_to"] = NOW
    with pytest.raises(ValidationError, match="window must be ordered"):
        Citation.model_validate(citation_values)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("bm25_pair", "BM25 rank and score"),
        ("vector_pair", "vector rank and score"),
    ],
)
def test_evidence_retrieval_provenance_requires_rank_score_pairs(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
    message: str,
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    packet = asyncio.run(evidence_hub(checker).build(request))
    values = packet.evidence[0].retrieval.model_dump()
    values["vector_rank"] = 1
    values["vector_score"] = 0.5
    if mutation == "bm25_pair":
        values["bm25_score"] = None
    else:
        values["vector_score"] = None

    with pytest.raises(ValidationError, match=message):
        EvidenceRetrievalProvenance.model_validate(values)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_vector", "requires vector provenance"),
        ("wrong_reason", "degradation reason disagree"),
        ("bm25_branch", "BM25 provenance"),
        ("bm25_space", "BM25 provenance cannot"),
        ("vector_branch", "vector provenance"),
        ("vector_space", "vector provenance requires"),
        ("manifest", "one chunk manifest"),
        ("reranker_binding", "requires a trusted binding"),
        ("fallback", "explicit degradation"),
        ("empty", "cannot claim reranker"),
    ],
)
def test_evidence_pipeline_provenance_rejects_inconsistent_modes(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
    message: str,
) -> None:
    request, _ = reranking(context_factory, fused_candidate(1, "a"))
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(check_request, RevocationStatus.CLEAR)
    )
    packet = asyncio.run(evidence_hub(checker).build(request))
    values = packet.pipeline.model_dump()
    if mutation == "missing_vector":
        values["vector"] = None
    elif mutation == "wrong_reason":
        values["vector_degradation_reason"] = "VECTOR_RECALL_UNAVAILABLE"
    elif mutation == "bm25_branch":
        cast(dict[str, object], values["bm25"])["branch"] = "VECTOR"
    elif mutation == "bm25_space":
        cast(dict[str, object], values["bm25"])["embedding_space_fingerprint"] = {
            "fingerprint": "4" * 64,
            "dimension": 2,
            "distance": "COSINE",
            "normalized": True,
            "vector_data_type": "FLOAT32",
        }
    elif mutation == "vector_branch":
        cast(dict[str, object], values["vector"])["branch"] = "BM25"
    elif mutation == "vector_space":
        cast(dict[str, object], values["vector"])["embedding_space_fingerprint"] = None
    elif mutation == "manifest":
        cast(dict[str, object], values["vector"])["chunk_manifest_hash"] = "9" * 64
    elif mutation == "reranker_binding":
        values["reranker_binding"] = None
    elif mutation == "fallback":
        values.update(
            reranking_mode="RRF_FALLBACK",
            reranker_binding=None,
            reranker_degradation_reason="NONE",
        )
    else:
        values.update(reranking_mode="EMPTY")

    with pytest.raises(ValidationError, match=message):
        EvidencePipelineProvenance.model_validate(values)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("naive_time", "timestamps must include"),
        ("status", "status must reflect"),
        ("count", "counts must cover"),
        ("missing_snapshot", "requires a content revocation snapshot"),
        ("execution_validity", "must outlive evidence selection"),
        ("content_validity", "must outlive evidence selection"),
        ("empty_mode", "must match an empty evidence input"),
        ("duplicate_evidence_id", "repeat an evidence ID"),
        ("duplicate_chunk", "repeat a chunk"),
        ("duplicate_rrf_rank", "repeat an RRF rank"),
        ("duplicate_reranker_rank", "repeat a reranker rank"),
        ("not_effective", "not effective yet"),
        ("expired", "no longer effective"),
        ("bm25_only_vector", "BM25-only evidence"),
        ("reranked_score", "requires a reranker score"),
        ("fallback_score", "non-reranked evidence"),
    ],
)
def test_evidence_packet_rejects_inconsistent_scope_and_pipeline_state(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
    message: str,
) -> None:
    request, _ = reranking(
        context_factory,
        fused_candidate(1, "a"),
        fused_candidate(2, "b"),
    )
    checker = RespondingEvidenceRevocationChecker(
        lambda check_request: revocation_result(
            check_request,
            RevocationStatus.CLEAR,
            RevocationStatus.CLEAR,
        )
    )
    packet = asyncio.run(evidence_hub(checker).build(request))
    values = packet.model_dump()
    evidence_values = cast(list[dict[str, object]], values["evidence"])
    if mutation == "naive_time":
        values["effective_at"] = datetime(2026, 8, 11, 8, 0)
    elif mutation == "status":
        values["status"] = "EMPTY"
    elif mutation == "count":
        values["input_candidate_count"] = 3
    elif mutation == "missing_snapshot":
        values["content_revocation_snapshot_version"] = None
        values["content_revocation_valid_until"] = None
    elif mutation == "execution_validity":
        values["execution_revocation_valid_until"] = NOW
    elif mutation == "content_validity":
        values["content_revocation_valid_until"] = NOW
    elif mutation == "empty_mode":
        pipeline = cast(dict[str, object], values["pipeline"])
        pipeline.update(
            reranking_mode="EMPTY",
            reranker_degradation_reason="NONE",
            reranker_binding=None,
        )
    elif mutation == "duplicate_evidence_id":
        evidence_values[1]["evidence_id"] = evidence_values[0]["evidence_id"]
    elif mutation == "duplicate_chunk":
        evidence_values[1]["chunk_id"] = evidence_values[0]["chunk_id"]
    elif mutation == "duplicate_rrf_rank":
        cast(dict[str, object], evidence_values[1]["retrieval"])["rrf_rank"] = 1
    elif mutation == "duplicate_reranker_rank":
        cast(dict[str, object], evidence_values[1]["retrieval"])["reranker_rank"] = 1
    elif mutation == "not_effective":
        cast(dict[str, object], evidence_values[0]["citation"])["effective_from"] = NOW + (
            timedelta(seconds=1)
        )
    elif mutation == "expired":
        cast(dict[str, object], evidence_values[0]["citation"])["effective_to"] = NOW
    elif mutation == "bm25_only_vector":
        pipeline = cast(dict[str, object], values["pipeline"])
        pipeline.update(
            retrieval_execution_mode="BM25_ONLY",
            vector_degradation_reason="VECTOR_RECALL_UNAVAILABLE",
            vector=None,
        )
        retrieval_values = cast(dict[str, object], evidence_values[0]["retrieval"])
        retrieval_values.update(vector_rank=1, vector_score=0.5)
    elif mutation == "reranked_score":
        cast(dict[str, object], evidence_values[0]["retrieval"])["reranker_score"] = None
    else:
        pipeline = cast(dict[str, object], values["pipeline"])
        pipeline.update(
            reranking_mode="RRF_FALLBACK",
            reranker_degradation_reason="RERANKER_UNAVAILABLE",
            reranker_binding=None,
        )

    with pytest.raises(ValidationError, match=message):
        EvidencePacket.model_validate(values)


def test_evidence_hub_requires_a_positive_revocation_ttl() -> None:
    with pytest.raises(ValueError, match="TTL must be positive"):
        EvidenceHub(
            ScriptedEvidenceRevocationChecker([]),
            max_revocation_ttl=timedelta(0),
        )
