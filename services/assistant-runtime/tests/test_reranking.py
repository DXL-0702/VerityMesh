import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from support.retrieval import MutableClock, ScriptedReranker, chunk, retrieval_request
from veritymesh_assistant_runtime.execution_context import (
    AccessSegment,
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.reranking import (
    RankedRetrievalCandidate,
    RerankerBinding,
    RerankerDegradationReason,
    RerankerPort,
    RerankerRequest,
    RerankerResult,
    RerankerResultItem,
    RerankingKernel,
    RerankingMode,
    RerankingRequest,
    RerankingResult,
    RerankingScopeRejected,
    reranker_candidate_set_fingerprint,
)
from veritymesh_assistant_runtime.retrieval import (
    FusedRetrievalCandidate,
    HybridRetrievalResult,
    RecallBranch,
    RecallProvenance,
    RetrievalExecutionMode,
    VectorDegradationReason,
)

CONFIGURATION_FINGERPRINT = "6" * 64


def binding() -> RerankerBinding:
    return RerankerBinding(
        logical_model="reranker-primary",
        provider="aliyun-bailian",
        region="cn-beijing",
        api_mode="native",
        model="qwen3-rerank",
        revision="rerank-revision-1",
        configuration_fingerprint=CONFIGURATION_FINGERPRINT,
    )


def candidate(rank: int, chunk_id: str) -> FusedRetrievalCandidate:
    return FusedRetrievalCandidate(
        rank=rank,
        rrf_score=1 / (60 + rank),
        chunk=chunk(chunk_id),
        bm25_rank=rank,
        bm25_score=10.0 - rank,
        bm25_highlight=None,
        vector_rank=None,
        vector_score=None,
    )


def reranking_request(
    context_factory: Callable[..., ProjectExecutionContext],
    *candidates: FusedRetrievalCandidate,
) -> RerankingRequest:
    request = retrieval_request(context_factory)
    return RerankingRequest(
        context=request.context,
        plan=request.plan,
        retrieval=HybridRetrievalResult(
            schema_version="1.0",
            message_execution_id=request.plan.message_execution_id,
            filters=request.plan.filters,
            execution_mode=RetrievalExecutionMode.HYBRID,
            vector_degradation_reason=VectorDegradationReason.NONE,
            bm25_provenance=RecallProvenance(
                branch=RecallBranch.BM25,
                projection_watermark="bm25-watermark-1",
                chunk_manifest_hash="1" * 64,
                projection_configuration_fingerprint="2" * 64,
                embedding_space_fingerprint=None,
            ),
            vector_provenance=RecallProvenance(
                branch=RecallBranch.VECTOR,
                projection_watermark="vector-watermark-1",
                chunk_manifest_hash="1" * 64,
                projection_configuration_fingerprint="3" * 64,
                embedding_space_fingerprint=request.projections.embedding_space_fingerprint,
            ),
            candidates=candidates,
        ),
        binding=binding(),
    )


def reranking_kernel(
    port: RerankerPort,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
) -> RerankingKernel:
    return RerankingKernel(port, clock=clock)


def result_for(request: RerankingRequest, *items: RerankerResultItem) -> RerankerResult:
    return RerankerResult(
        message_execution_id=request.plan.message_execution_id,
        candidate_set_fingerprint=reranker_candidate_set_fingerprint(request.retrieval.candidates),
        binding=request.binding,
        items=items,
    )


def test_reranking_uses_minimal_provider_input_and_preserves_rrf_provenance(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"), candidate(2, "b"))
    response = result_for(
        request,
        RerankerResultItem(rank=1, input_rank=2, score=0.93),
        RerankerResultItem(rank=2, input_rank=1, score=0.75),
    )
    port = ScriptedReranker([response])

    result = asyncio.run(reranking_kernel(port).rerank(request))

    assert result.mode is RerankingMode.RERANKER
    assert result.degradation_reason is RerankerDegradationReason.NONE
    assert result.binding == request.binding
    assert [item.candidate.chunk.chunk_id for item in result.candidates] == ["b", "a"]
    assert result.candidates[0].rank == 1
    assert result.candidates[0].candidate.rank == 2
    assert result.candidates[0].reranker_score == 0.93
    assert result.candidates[1].candidate.rrf_score == pytest.approx(1 / 61)

    provider_request = port.requests[0]
    assert provider_request.message_execution_id == "msg-exec-1"
    assert provider_request.top_k == 10
    assert provider_request.binding == request.binding
    assert [(item.input_rank, item.chunk_id) for item in provider_request.candidates] == [
        (1, "a"),
        (2, "b"),
    ]
    assert provider_request.model_dump().keys() == {
        "normalized_query",
        "message_execution_id",
        "candidate_set_fingerprint",
        "candidates",
        "top_k",
        "binding",
        "deadline_at",
        "deadline_remaining",
        "audit",
    }
    assert {"project_id", "access_context_hash", "citation_url"}.isdisjoint(
        provider_request.model_dump()
    )


@pytest.mark.parametrize(
    ("outcome_factory", "reason"),
    [
        (
            lambda request: RuntimeError("provider unavailable"),
            RerankerDegradationReason.RERANKER_UNAVAILABLE,
        ),
        (
            lambda request: RerankerResult(
                message_execution_id=request.plan.message_execution_id,
                candidate_set_fingerprint="9" * 64,
                binding=request.binding,
                items=(RerankerResultItem(rank=1, input_rank=1, score=0.9),),
            ),
            RerankerDegradationReason.RERANKER_CONTRACT_REJECTED,
        ),
    ],
)
def test_reranker_failure_or_contract_mismatch_falls_back_to_rrf_top_ten(
    context_factory: Callable[..., ProjectExecutionContext],
    outcome_factory: Callable[[RerankingRequest], RerankerResult | Exception],
    reason: RerankerDegradationReason,
) -> None:
    request = reranking_request(
        context_factory,
        *(candidate(rank, f"chunk-{rank}") for rank in range(1, 12)),
    )
    result = asyncio.run(
        reranking_kernel(ScriptedReranker([outcome_factory(request)])).rerank(request)
    )

    assert result.mode is RerankingMode.RRF_FALLBACK
    assert result.degradation_reason is reason
    assert result.binding is None
    assert [item.candidate.chunk.chunk_id for item in result.candidates] == [
        f"chunk-{rank}" for rank in range(1, 11)
    ]
    assert all(item.reranker_score is None for item in result.candidates)


def test_empty_retrieval_does_not_call_the_reranker(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory)
    port = ScriptedReranker([])

    result = asyncio.run(reranking_kernel(port).rerank(request))

    assert result.mode is RerankingMode.EMPTY
    assert result.candidates == ()
    assert port.requests == []


@pytest.mark.parametrize(
    "mutation",
    ["binding", "execution", "candidate_set", "unknown_input", "wrong_size"],
)
def test_invalid_provider_results_cannot_change_candidate_selection(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"), candidate(2, "b"))
    values = result_for(
        request,
        RerankerResultItem(rank=1, input_rank=1, score=0.9),
        RerankerResultItem(rank=2, input_rank=2, score=0.8),
    ).model_dump()
    if mutation == "binding":
        cast(dict[str, object], values["binding"])["revision"] = "unexpected-revision"
    elif mutation == "execution":
        values["message_execution_id"] = "another-execution"
    elif mutation == "candidate_set":
        values["candidate_set_fingerprint"] = "8" * 64
    elif mutation == "unknown_input":
        cast(list[dict[str, object]], values["items"])[0]["input_rank"] = 3
    else:
        values["items"] = [cast(list[dict[str, object]], values["items"])[0]]
    invalid = RerankerResult.model_validate(values)

    result = asyncio.run(reranking_kernel(ScriptedReranker([invalid])).rerank(request))

    assert result.mode is RerankingMode.RRF_FALLBACK
    assert result.degradation_reason is RerankerDegradationReason.RERANKER_CONTRACT_REJECTED


def test_scope_mismatch_prevents_a_reranker_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))
    invalid = RerankingRequest(
        context=request.context,
        plan=request.plan.model_copy(update={"message_execution_id": "another-execution"}),
        retrieval=request.retrieval,
        binding=request.binding,
    )
    port = ScriptedReranker([])

    with pytest.raises(RerankingScopeRejected):
        asyncio.run(reranking_kernel(port).rerank(invalid))
    assert port.requests == []


@pytest.mark.parametrize(
    "mutation",
    [
        "retrieval_scope",
        "retrieval_manifest",
        "retrieval_access",
        "retrieval_effective_window",
        "retrieval_rrf_score",
    ],
)
def test_unvalidated_reranking_inputs_cannot_send_a_chunk_to_the_provider(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))
    if mutation == "retrieval_scope":
        invalid = RerankingRequest(
            context=request.context,
            plan=request.plan,
            retrieval=request.retrieval.model_copy(
                update={
                    "filters": request.retrieval.filters.model_copy(update={"project_id": "other"})
                }
            ),
            binding=request.binding,
        )
    elif mutation == "retrieval_manifest":
        invalid = RerankingRequest(
            context=request.context,
            plan=request.plan,
            retrieval=request.retrieval.model_copy(
                update={
                    "candidates": (
                        request.retrieval.candidates[0].model_copy(
                            update={
                                "chunk": request.retrieval.candidates[0].chunk.model_copy(
                                    update={"chunk_manifest_hash": "9" * 64}
                                )
                            }
                        ),
                    )
                }
            ),
            binding=request.binding,
        )
    elif mutation == "retrieval_access":
        invalid = RerankingRequest(
            context=request.context,
            plan=request.plan,
            retrieval=request.retrieval.model_copy(
                update={
                    "candidates": (
                        request.retrieval.candidates[0].model_copy(
                            update={
                                "chunk": request.retrieval.candidates[0].chunk.model_copy(
                                    update={"access_segment": AccessSegment.PUBLIC}
                                )
                            }
                        ),
                    )
                }
            ),
            binding=request.binding,
        )
    elif mutation == "retrieval_effective_window":
        invalid = RerankingRequest(
            context=request.context,
            plan=request.plan,
            retrieval=request.retrieval.model_copy(
                update={
                    "candidates": (
                        request.retrieval.candidates[0].model_copy(
                            update={
                                "chunk": request.retrieval.candidates[0].chunk.model_copy(
                                    update={"effective_to": NOW}
                                )
                            }
                        ),
                    )
                }
            ),
            binding=request.binding,
        )
    elif mutation == "retrieval_rrf_score":
        invalid = RerankingRequest(
            context=request.context,
            plan=request.plan,
            retrieval=request.retrieval.model_copy(
                update={
                    "candidates": (
                        request.retrieval.candidates[0].model_copy(update={"rrf_score": 0.9}),
                    )
                }
            ),
            binding=request.binding,
        )
    else:
        raise AssertionError(f"unsupported mutation: {mutation}")
    port = ScriptedReranker([])

    with pytest.raises(RerankingScopeRejected):
        asyncio.run(reranking_kernel(port).rerank(invalid))
    assert port.requests == []


def test_clearance_expiry_and_deadline_take_precedence_after_the_port_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))
    clock = MutableClock(NOW)

    class LateFailure:
        async def rerank(self, _request: RerankerRequest) -> RerankerResult:
            clock.current = NOW + timedelta(seconds=3)
            raise RuntimeError("timeout")

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(reranking_kernel(LateFailure(), clock=clock).rerank(request))


def test_cancellation_is_not_converted_into_an_rrf_fallback(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))

    class CancelledReranker:
        async def rerank(self, _request: RerankerRequest) -> RerankerResult:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(reranking_kernel(CancelledReranker()).rerank(request))


def test_reranker_provider_timeout_uses_rrf_fallback(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))

    class TimeoutReranker:
        async def rerank(self, _request: RerankerRequest) -> RerankerResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout reranker unexpectedly returned")

    result = asyncio.run(reranking_kernel(TimeoutReranker()).rerank(request))

    assert result.mode is RerankingMode.RRF_FALLBACK
    assert result.degradation_reason is RerankerDegradationReason.RERANKER_UNAVAILABLE


def test_reranker_provider_deadline_error_propagates(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))

    class DeadlineReranker:
        async def rerank(self, _request: RerankerRequest) -> RerankerResult:
            raise ExecutionDeadlineExceeded

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(reranking_kernel(DeadlineReranker()).rerank(request))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("request_empty", "requires at least one"),
        ("request_overflow", "cannot exceed"),
        ("request_rank", "input ranks"),
        ("request_duplicate", "cannot repeat a chunk"),
        ("result_rank", "result ranks"),
        ("result_duplicate", "repeat an input rank"),
    ],
)
def test_reranker_contract_models_reject_invalid_shapes(
    mutation: str,
    message: str,
) -> None:
    if mutation.startswith("request"):
        candidates = [
            {
                "input_rank": 1,
                "chunk_id": "chunk-1",
                "title": "Title",
                "section": "Section",
                "chunk_text": "Text",
            }
        ]
        if mutation == "request_empty":
            candidates = []
        elif mutation == "request_overflow":
            candidates = [
                {
                    "input_rank": rank,
                    "chunk_id": f"chunk-{rank}",
                    "title": "Title",
                    "section": "Section",
                    "chunk_text": "Text",
                }
                for rank in range(1, 52)
            ]
        elif mutation == "request_rank":
            candidates[0]["input_rank"] = 2
        elif mutation == "request_duplicate":
            candidates.append(
                {
                    "input_rank": 2,
                    "chunk_id": "chunk-1",
                    "title": "Title",
                    "section": "Section",
                    "chunk_text": "Text",
                }
            )
        values = {
            "normalized_query": "query",
            "message_execution_id": "msg-exec-1",
            "candidate_set_fingerprint": "1" * 64,
            "candidates": candidates,
            "top_k": 10,
            "binding": binding().model_dump(),
            "deadline_at": NOW,
            "deadline_remaining": timedelta(seconds=1),
            "audit": {"trace_id": "trace-1", "request_id": "request-1"},
        }
        model: type[RerankerRequest] | type[RerankerResult] = RerankerRequest
    else:
        values = {
            "message_execution_id": "msg-exec-1",
            "candidate_set_fingerprint": "1" * 64,
            "binding": binding().model_dump(),
            "items": (
                [{"rank": 2, "input_rank": 1, "score": 0.9}]
                if mutation == "result_rank"
                else [
                    {"rank": 1, "input_rank": 1, "score": 0.9},
                    {"rank": 2, "input_rank": 1, "score": 0.8},
                ]
            ),
        }
        model = RerankerResult

    with pytest.raises(ValidationError, match=message):
        model.model_validate(values)


def test_reranking_result_models_enforce_mode_consistency(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"))
    valid = asyncio.run(
        reranking_kernel(
            ScriptedReranker(
                [result_for(request, RerankerResultItem(rank=1, input_rank=1, score=0.9))]
            )
        ).rerank(request)
    )
    values = valid.model_dump()
    values["binding"] = None

    with pytest.raises(ValidationError, match="reranker mode requires"):
        RerankingResult.model_validate(values)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("overflow", "Top 10"),
        ("rank", "output ranks"),
        ("duplicate_chunk", "repeat a chunk"),
        ("duplicate_rrf_rank", "repeat an RRF rank"),
        ("missing_vector", "requires vector provenance"),
        ("wrong_reason", "degradation reason disagree"),
        ("bm25_branch", "BM25 provenance"),
        ("bm25_space", "BM25 provenance cannot"),
        ("vector_branch", "vector provenance"),
        ("vector_space", "vector provenance requires"),
        ("manifest", "one chunk manifest"),
        ("bm25_only_vector", "BM25-only reranking"),
        ("fallback_empty", "RRF fallback requires"),
        ("fallback_reordered", "RRF fallback requires"),
        ("empty_binding", "empty reranking"),
    ],
)
def test_reranking_result_rejects_inconsistent_pipeline_provenance(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
    message: str,
) -> None:
    request = reranking_request(context_factory, candidate(1, "a"), candidate(2, "b"))
    valid = asyncio.run(
        reranking_kernel(
            ScriptedReranker(
                [
                    result_for(
                        request,
                        RerankerResultItem(rank=1, input_rank=1, score=0.9),
                        RerankerResultItem(rank=2, input_rank=2, score=0.8),
                    )
                ]
            )
        ).rerank(request)
    )
    values = valid.model_dump()
    candidates = cast(list[dict[str, object]], values["candidates"])
    if mutation == "overflow":
        values["candidates"] = [
            RankedRetrievalCandidate(
                rank=rank,
                candidate=candidate(rank, f"overflow-{rank}"),
                reranker_score=1.0 / rank,
            ).model_dump()
            for rank in range(1, 12)
        ]
    elif mutation == "rank":
        candidates[0]["rank"] = 2
    elif mutation == "duplicate_chunk":
        cast(dict[str, object], candidates[1]["candidate"])["chunk"] = cast(
            dict[str, object], candidates[0]["candidate"]
        )["chunk"]
    elif mutation == "duplicate_rrf_rank":
        cast(dict[str, object], candidates[1]["candidate"])["rank"] = 1
    elif mutation == "missing_vector":
        values["vector_provenance"] = None
    elif mutation == "wrong_reason":
        values["vector_degradation_reason"] = "VECTOR_RECALL_UNAVAILABLE"
    elif mutation == "bm25_branch":
        cast(dict[str, object], values["bm25_provenance"])["branch"] = "VECTOR"
    elif mutation == "bm25_space":
        cast(dict[str, object], values["bm25_provenance"])["embedding_space_fingerprint"] = {
            "fingerprint": "4" * 64,
            "dimension": 2,
            "distance": "COSINE",
            "normalized": True,
            "vector_data_type": "FLOAT32",
        }
    elif mutation == "vector_branch":
        cast(dict[str, object], values["vector_provenance"])["branch"] = "BM25"
    elif mutation == "vector_space":
        cast(dict[str, object], values["vector_provenance"])["embedding_space_fingerprint"] = None
    elif mutation == "manifest":
        cast(dict[str, object], values["vector_provenance"])["chunk_manifest_hash"] = "9" * 64
    elif mutation == "bm25_only_vector":
        values["retrieval_execution_mode"] = "BM25_ONLY"
        values["vector_degradation_reason"] = "VECTOR_RECALL_UNAVAILABLE"
        values["vector_provenance"] = None
        cast(dict[str, object], candidates[0]["candidate"])["vector_rank"] = 1
        cast(dict[str, object], candidates[0]["candidate"])["vector_score"] = 0.5
    elif mutation == "fallback_empty":
        values.update(
            mode="RRF_FALLBACK",
            degradation_reason="RERANKER_UNAVAILABLE",
            binding=None,
            candidates=[],
        )
    elif mutation == "fallback_reordered":
        values.update(
            mode="RRF_FALLBACK",
            degradation_reason="RERANKER_UNAVAILABLE",
            binding=None,
        )
        candidates[0]["reranker_score"] = None
        candidates[1]["reranker_score"] = None
        cast(dict[str, object], candidates[0]["candidate"])["rank"] = 2
        cast(dict[str, object], candidates[1]["candidate"])["rank"] = 1
    else:
        values.update(mode="EMPTY", candidates=[])

    with pytest.raises(ValidationError, match=message):
        RerankingResult.model_validate(values)


def test_ranked_candidate_preserves_the_inner_rrf_candidate() -> None:
    ranked = RankedRetrievalCandidate(
        rank=1,
        candidate=candidate(3, "a"),
        reranker_score=0.9,
    )

    assert ranked.rank == 1
    assert ranked.candidate.rank == 3
