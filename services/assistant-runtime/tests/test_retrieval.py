import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from support.retrieval import (
    BM25_CONFIGURATION,
    EMBEDDING_SPACE,
    MANIFEST_HASH,
    MutableClock,
    ScriptedBm25Recall,
    ScriptedQueryEmbedding,
    ScriptedVectorRecall,
    chunk,
    embedding_result,
    kernel,
    projection_set,
    query_plan,
    recall_result,
    retrieval_request,
)
from veritymesh_assistant_runtime.execution_context import (
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.retrieval import (
    Bm25RecallContractRejected,
    Bm25RecallRequest,
    Bm25RecallUnavailable,
    EmbeddingSpaceFingerprint,
    FusedRetrievalCandidate,
    HybridRetrievalRequest,
    HybridRetrievalResult,
    InvalidFusionConfiguration,
    QueryEmbeddingRequest,
    QueryEmbeddingResult,
    RecallBranch,
    RecallHit,
    RecallProvenance,
    RecallResult,
    RetrievalChunk,
    RetrievalExecutionMode,
    RetrievalProjectionConflict,
    RetrievalProjectionSet,
    RetrievalScopeRejected,
    VectorDegradationReason,
    VectorRecallRequest,
    reciprocal_rank_fusion,
)
from veritymesh_assistant_runtime.revocation import (
    RevocationClearedExecutionContext,
    RevocationStateUnavailable,
)


def test_hybrid_retrieval_runs_both_ports_and_preserves_fusion_evidence(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    chunk_a = chunk("a")
    chunk_b = chunk("b")
    chunk_c = chunk("c")
    bm25_result = recall_result(
        request.plan,
        RecallBranch.BM25,
        (
            RecallHit(chunk=chunk_a, rank=1, score=8.5, highlight="<em>API</em>"),
            RecallHit(chunk=chunk_b, rank=2, score=7.0),
        ),
    )
    vector_result = recall_result(
        request.plan,
        RecallBranch.VECTOR,
        (
            RecallHit(chunk=chunk_b, rank=1, score=0.92),
            RecallHit(chunk=chunk_c, rank=2, score=0.88),
        ),
    )
    embedding = ScriptedQueryEmbedding([embedding_result()])
    bm25 = ScriptedBm25Recall([bm25_result])
    vector = ScriptedVectorRecall([vector_result])

    result = asyncio.run(kernel(embedding, bm25, vector).retrieve(request))

    assert result.execution_mode is RetrievalExecutionMode.HYBRID
    assert result.vector_degradation_reason is VectorDegradationReason.NONE
    assert [candidate.chunk.chunk_id for candidate in result.candidates] == ["b", "a", "c"]
    assert result.candidates[0].bm25_rank == 2
    assert result.candidates[0].bm25_score == 7.0
    assert result.candidates[0].vector_rank == 1
    assert result.candidates[0].vector_score == 0.92
    assert result.candidates[1].bm25_highlight == "<em>API</em>"
    assert result.bm25_provenance.projection_watermark == "bm25-watermark-1"
    assert result.vector_provenance is not None
    assert result.vector_provenance.embedding_space_fingerprint == EMBEDDING_SPACE

    assert embedding.requests == [
        QueryEmbeddingRequest(
            normalized_query=request.plan.normalized_query,
            locale="zh-CN",
            expected_embedding_space_fingerprint=EMBEDDING_SPACE,
            message_execution_id="msg-exec-1",
            deadline_at=request.context.context.deadline_at,
            deadline_remaining=timedelta(seconds=2),
            audit=request.context.context.audit,
        )
    ]
    assert bm25.requests == [
        Bm25RecallRequest(
            normalized_query=request.plan.normalized_query,
            filters=request.plan.filters,
            projection=request.projections.bm25,
            top_k=50,
            message_execution_id="msg-exec-1",
            deadline_at=request.context.context.deadline_at,
            deadline_remaining=timedelta(seconds=2),
            audit=request.context.context.audit,
        )
    ]
    assert vector.requests == [
        VectorRecallRequest(
            query_vector=(1.0, 0.0),
            embedding_space_fingerprint=EMBEDDING_SPACE,
            filters=request.plan.filters,
            projection=request.projections.vector,
            top_k=50,
            message_execution_id="msg-exec-1",
            deadline_at=request.context.context.deadline_at,
            deadline_remaining=timedelta(seconds=2),
            audit=request.context.context.audit,
        )
    ]


def test_recall_branches_are_started_concurrently(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    bm25_result = recall_result(request.plan, RecallBranch.BM25, ())
    vector_result = recall_result(request.plan, RecallBranch.VECTOR, ())

    async def scenario() -> HybridRetrievalResult:
        bm25_started = asyncio.Event()
        embedding_started = asyncio.Event()

        class CoordinatedBm25:
            async def recall(self, _request: Bm25RecallRequest) -> RecallResult:
                bm25_started.set()
                await embedding_started.wait()
                return bm25_result

        class CoordinatedEmbedding:
            async def embed_query(self, _request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
                embedding_started.set()
                await bm25_started.wait()
                return embedding_result()

        return await asyncio.wait_for(
            kernel(
                CoordinatedEmbedding(),
                CoordinatedBm25(),
                ScriptedVectorRecall([vector_result]),
            ).retrieve(request),
            timeout=1,
        )

    result = asyncio.run(scenario())

    assert result.execution_mode is RetrievalExecutionMode.HYBRID


@pytest.mark.parametrize(
    ("embedding_outcome", "vector_outcome", "expected_reason"),
    [
        (
            RuntimeError("embedding provider unavailable"),
            None,
            VectorDegradationReason.QUERY_EMBEDDING_UNAVAILABLE,
        ),
        (
            QueryEmbeddingResult(
                vector=(1.0, 0.0),
                embedding_space_fingerprint=EmbeddingSpaceFingerprint(
                    fingerprint="9" * 64,
                    dimension=2,
                ),
            ),
            None,
            VectorDegradationReason.QUERY_EMBEDDING_CONTRACT_REJECTED,
        ),
        (
            embedding_result(),
            RuntimeError("vector store unavailable"),
            VectorDegradationReason.VECTOR_RECALL_UNAVAILABLE,
        ),
    ],
)
def test_vector_branch_failures_degrade_to_bm25_only(
    context_factory: Callable[..., ProjectExecutionContext],
    embedding_outcome: QueryEmbeddingResult | Exception,
    vector_outcome: RecallResult | Exception | None,
    expected_reason: VectorDegradationReason,
) -> None:
    request = retrieval_request(context_factory)
    bm25_result = recall_result(
        request.plan,
        RecallBranch.BM25,
        (RecallHit(chunk=chunk("a"), rank=1, score=2.0),),
    )
    embedding = ScriptedQueryEmbedding([embedding_outcome])
    vector = ScriptedVectorRecall([] if vector_outcome is None else [vector_outcome])

    result = asyncio.run(
        kernel(embedding, ScriptedBm25Recall([bm25_result]), vector).retrieve(request)
    )

    assert result.execution_mode is RetrievalExecutionMode.BM25_ONLY
    assert result.vector_degradation_reason is expected_reason
    assert result.vector_provenance is None
    assert [candidate.chunk.chunk_id for candidate in result.candidates] == ["a"]
    assert len(vector.requests) == (0 if vector_outcome is None else 1)


@pytest.mark.parametrize("mismatch", ["scope", "manifest", "configuration", "space", "top_k"])
def test_invalid_vector_results_are_discarded_before_fusion(
    context_factory: Callable[..., ProjectExecutionContext],
    mismatch: str,
) -> None:
    request = retrieval_request(context_factory)
    bm25_result = recall_result(request.plan, RecallBranch.BM25, ())
    values = recall_result(request.plan, RecallBranch.VECTOR, ()).model_dump()
    if mismatch == "scope":
        filters = request.plan.filters.model_dump()
        filters["project_id"] = "another-project"
        values["filters"] = filters
    elif mismatch == "manifest":
        values["chunk_manifest_hash"] = "6" * 64
    elif mismatch == "configuration":
        values["projection_configuration_fingerprint"] = "7" * 64
    elif mismatch == "space":
        values["embedding_space_fingerprint"] = {
            "fingerprint": "8" * 64,
            "dimension": 2,
            "distance": "COSINE",
            "normalized": True,
            "vector_data_type": "FLOAT32",
        }
    else:
        values["hits"] = [
            RecallHit(chunk=chunk(f"overflow-{index}"), rank=index + 1, score=1.0).model_dump()
            for index in range(51)
        ]
    vector_result = RecallResult.model_validate(values)

    result = asyncio.run(
        kernel(
            ScriptedQueryEmbedding([embedding_result()]),
            ScriptedBm25Recall([bm25_result]),
            ScriptedVectorRecall([vector_result]),
        ).retrieve(request)
    )

    assert result.execution_mode is RetrievalExecutionMode.BM25_ONLY
    assert result.vector_degradation_reason is VectorDegradationReason.VECTOR_CONTRACT_REJECTED


def test_bm25_failure_aborts_retrieval_instead_of_using_vector_only(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    failure = RuntimeError("elasticsearch unavailable")

    with pytest.raises(Bm25RecallUnavailable) as raised:
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([embedding_result()]),
                ScriptedBm25Recall([failure]),
                ScriptedVectorRecall([recall_result(request.plan, RecallBranch.VECTOR, ())]),
            ).retrieve(request)
        )

    assert raised.value.__cause__ is failure


def test_bm25_provider_timeout_aborts_retrieval(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)

    class TimeoutBm25:
        async def recall(self, _request: Bm25RecallRequest) -> RecallResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout BM25 provider unexpectedly returned")

    with pytest.raises(Bm25RecallUnavailable):
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([embedding_result()]),
                TimeoutBm25(),
                ScriptedVectorRecall([recall_result(request.plan, RecallBranch.VECTOR, ())]),
            ).retrieve(request)
        )


def test_bm25_provider_deadline_error_propagates(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)

    class DeadlineBm25:
        async def recall(self, _request: Bm25RecallRequest) -> RecallResult:
            raise ExecutionDeadlineExceeded

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([embedding_result()]),
                DeadlineBm25(),
                ScriptedVectorRecall([]),
            ).retrieve(request)
        )


def test_vector_provider_timeouts_degrade_vector_branch(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)

    class TimeoutEmbedding:
        async def embed_query(self, _request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout embedding provider unexpectedly returned")

    class TimeoutVector:
        async def recall(self, _request: VectorRecallRequest) -> RecallResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout vector provider unexpectedly returned")

    bm25 = recall_result(request.plan, RecallBranch.BM25, ())
    embedding_result_after_timeout = asyncio.run(
        kernel(
            TimeoutEmbedding(),
            ScriptedBm25Recall([bm25]),
            ScriptedVectorRecall([]),
        ).retrieve(request)
    )
    assert (
        embedding_result_after_timeout.vector_degradation_reason
        is VectorDegradationReason.QUERY_EMBEDDING_UNAVAILABLE
    )

    vector_request = HybridRetrievalRequest(
        context=request.context,
        plan=request.plan,
        projections=request.projections,
    )
    vector_result_after_timeout = asyncio.run(
        kernel(
            ScriptedQueryEmbedding([embedding_result()]),
            ScriptedBm25Recall([bm25]),
            TimeoutVector(),
        ).retrieve(vector_request)
    )
    assert (
        vector_result_after_timeout.vector_degradation_reason
        is VectorDegradationReason.VECTOR_RECALL_UNAVAILABLE
    )


def test_vector_provider_deadline_errors_propagate(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)

    class DeadlineEmbedding:
        async def embed_query(self, _request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
            raise ExecutionDeadlineExceeded

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(
            kernel(
                DeadlineEmbedding(),
                ScriptedBm25Recall([recall_result(request.plan, RecallBranch.BM25, ())]),
                ScriptedVectorRecall([]),
            ).retrieve(request)
        )

    class DeadlineVector:
        async def recall(self, _request: VectorRecallRequest) -> RecallResult:
            raise ExecutionDeadlineExceeded

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([embedding_result()]),
                ScriptedBm25Recall([recall_result(request.plan, RecallBranch.BM25, ())]),
                DeadlineVector(),
            ).retrieve(request)
        )

    class CancelledVector:
        async def recall(self, _request: VectorRecallRequest) -> RecallResult:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([embedding_result()]),
                ScriptedBm25Recall([recall_result(request.plan, RecallBranch.BM25, ())]),
                CancelledVector(),
            ).retrieve(request)
        )


def test_invalid_bm25_result_fails_closed(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    values = recall_result(request.plan, RecallBranch.BM25, ()).model_dump()
    values["message_execution_id"] = "another-execution"
    invalid_result = RecallResult.model_validate(values)

    with pytest.raises(Bm25RecallContractRejected):
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([embedding_result()]),
                ScriptedBm25Recall([invalid_result]),
                ScriptedVectorRecall([recall_result(request.plan, RecallBranch.VECTOR, ())]),
            ).retrieve(request)
        )


def test_request_scope_is_rechecked_before_any_port_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    mismatched_plan = request.plan.model_copy(update={"message_execution_id": "another-execution"})
    invalid_request = HybridRetrievalRequest(
        context=request.context,
        plan=mismatched_plan,
        projections=request.projections,
    )
    embedding = ScriptedQueryEmbedding([])
    bm25 = ScriptedBm25Recall([])
    vector = ScriptedVectorRecall([])

    with pytest.raises(RetrievalScopeRejected):
        asyncio.run(kernel(embedding, bm25, vector).retrieve(invalid_request))

    assert embedding.requests == []
    assert bm25.requests == []
    assert vector.requests == []


def test_expired_revocation_clearance_prevents_retrieval_calls(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    clock = MutableClock(NOW + timedelta(seconds=1))
    expired_context = RevocationClearedExecutionContext(
        guarded_context=request.context.guarded_context,
        revocation_scope=request.context.revocation_scope,
        revocation_snapshot_version=request.context.revocation_snapshot_version,
        revocation_checked_at=request.context.revocation_checked_at,
        revocation_valid_until=NOW + timedelta(seconds=1),
    )
    expired_request = HybridRetrievalRequest(
        context=expired_context,
        plan=query_plan(expired_context),
        projections=request.projections,
    )

    with pytest.raises(RevocationStateUnavailable):
        asyncio.run(
            kernel(
                ScriptedQueryEmbedding([]),
                ScriptedBm25Recall([]),
                ScriptedVectorRecall([]),
                clock=clock,
            ).retrieve(expired_request)
        )


def test_deadline_takes_precedence_over_a_late_vector_failure(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)
    clock = MutableClock(NOW)

    class LateFailingEmbedding:
        async def embed_query(self, _request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
            clock.current = NOW + timedelta(seconds=3)
            raise RuntimeError("provider timeout")

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(
            kernel(
                LateFailingEmbedding(),
                ScriptedBm25Recall([recall_result(request.plan, RecallBranch.BM25, ())]),
                ScriptedVectorRecall([]),
                clock=clock,
            ).retrieve(request)
        )


def test_cancellation_propagates_and_cancels_the_other_branch(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = retrieval_request(context_factory)

    async def scenario() -> None:
        bm25_started = asyncio.Event()
        bm25_cancelled = asyncio.Event()

        class BlockingBm25:
            async def recall(self, _request: Bm25RecallRequest) -> RecallResult:
                bm25_started.set()
                pending: asyncio.Future[RecallResult] = asyncio.get_running_loop().create_future()
                try:
                    return await pending
                finally:
                    bm25_cancelled.set()

        class CancellingEmbedding:
            async def embed_query(self, _request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
                await bm25_started.wait()
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await kernel(
                CancellingEmbedding(),
                BlockingBm25(),
                ScriptedVectorRecall([]),
            ).retrieve(request)
        assert bm25_cancelled.is_set()

    asyncio.run(scenario())


def test_rrf_uses_stable_chunk_id_ties_and_enforces_limits(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    plan = retrieval_request(context_factory).plan
    bm25 = recall_result(
        plan,
        RecallBranch.BM25,
        (RecallHit(chunk=chunk("b"), rank=1, score=100.0),),
    )
    vector = recall_result(
        plan,
        RecallBranch.VECTOR,
        (RecallHit(chunk=chunk("a"), rank=1, score=-100.0),),
    )

    fused = reciprocal_rank_fusion(bm25, vector, k=60, top_k=1)

    assert [candidate.chunk.chunk_id for candidate in fused] == ["a"]
    assert fused[0].rrf_score == pytest.approx(1 / 61)
    with pytest.raises(InvalidFusionConfiguration):
        reciprocal_rank_fusion(bm25, vector, k=0, top_k=1)


def test_rrf_rejects_conflicting_chunk_projections(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    plan = retrieval_request(context_factory).plan
    bm25 = recall_result(
        plan,
        RecallBranch.BM25,
        (RecallHit(chunk=chunk("shared"), rank=1, score=1.0),),
    )
    vector = recall_result(
        plan,
        RecallBranch.VECTOR,
        (RecallHit(chunk=chunk("shared", title="Changed title"), rank=1, score=1.0),),
    )

    with pytest.raises(RetrievalProjectionConflict):
        reciprocal_rank_fusion(bm25, vector, k=60, top_k=50)


@pytest.mark.parametrize(
    ("values_update", "message"),
    [
        ({"vector": (1.0,)}, "dimension does not match"),
        ({"vector": (0.5, 0.0)}, "not L2-normalized"),
        ({"vector": (float("nan"), 0.0)}, "finite number"),
    ],
)
def test_query_embedding_contract_rejects_invalid_vectors(
    values_update: dict[str, object],
    message: str,
) -> None:
    values = embedding_result().model_dump()
    values.update(values_update)

    with pytest.raises(ValidationError, match=message):
        QueryEmbeddingResult.model_validate(values)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"end_char": 0}, "greater than or equal to 1"),
        ({"start_char": 10}, "end offset must be after"),
        ({"effective_from": NOW, "effective_to": NOW}, "window must be ordered"),
        (
            {"effective_from": datetime(2026, 8, 11, 8, 0)},
            "must include a timezone",
        ),
    ],
)
def test_chunk_contract_rejects_invalid_offsets_and_windows(
    update: dict[str, object],
    message: str,
) -> None:
    values = chunk("a").model_dump()
    values.update(update)

    with pytest.raises(ValidationError, match=message):
        RetrievalChunk.model_validate(values)


def test_chunk_contract_allows_an_unbounded_effective_window() -> None:
    unbounded = chunk("unbounded", effective_from=None, effective_to=None)

    assert unbounded.effective_from is None
    assert unbounded.effective_to is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("branch_space", "only vector recall"),
        ("rank", "contiguous"),
        ("duplicate", "cannot repeat"),
        ("manifest", "result manifest"),
        ("scope", "project retrieval scope"),
        ("access", "access segment"),
        ("not_yet_effective", "not effective yet"),
        ("expired", "no longer effective"),
        ("vector_highlight", "lexical highlight"),
    ],
)
def test_recall_result_enforces_projection_boundaries(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
    message: str,
) -> None:
    plan = retrieval_request(context_factory).plan
    values = recall_result(
        plan,
        RecallBranch.BM25,
        (RecallHit(chunk=chunk("a"), rank=1, score=1.0),),
    ).model_dump()
    if mutation == "branch_space":
        values["embedding_space_fingerprint"] = EMBEDDING_SPACE.model_dump()
    elif mutation == "rank":
        cast(list[dict[str, object]], values["hits"])[0]["rank"] = 2
    elif mutation == "duplicate":
        values["hits"] = [
            RecallHit(chunk=chunk("a"), rank=1, score=1.0).model_dump(),
            RecallHit(chunk=chunk("a"), rank=2, score=0.5).model_dump(),
        ]
    elif mutation == "manifest":
        cast(list[dict[str, object]], values["hits"])[0]["chunk"][  # type: ignore[index]
            "chunk_manifest_hash"
        ] = "9" * 64
    elif mutation == "scope":
        cast(list[dict[str, object]], values["hits"])[0]["chunk"][  # type: ignore[index]
            "project_id"
        ] = "another-project"
    elif mutation == "access":
        cast(list[dict[str, object]], values["hits"])[0]["chunk"][  # type: ignore[index]
            "access_segment"
        ] = "PUBLIC"
    elif mutation == "not_yet_effective":
        cast(list[dict[str, object]], values["hits"])[0]["chunk"][  # type: ignore[index]
            "effective_from"
        ] = NOW + timedelta(seconds=1)
    elif mutation == "expired":
        cast(list[dict[str, object]], values["hits"])[0]["chunk"][  # type: ignore[index]
            "effective_to"
        ] = NOW
    else:
        values = recall_result(
            plan,
            RecallBranch.VECTOR,
            (RecallHit(chunk=chunk("a"), rank=1, score=1.0),),
        ).model_dump()
        cast(list[dict[str, object]], values["hits"])[0]["highlight"] = "match"

    with pytest.raises(ValidationError, match=message):
        RecallResult.model_validate(values)


def test_joint_projection_contract_requires_one_manifest() -> None:
    values = projection_set().model_dump()
    cast(dict[str, object], values["vector"])["chunk_manifest_hash"] = "9" * 64

    with pytest.raises(ValidationError, match="same chunk manifest"):
        RetrievalProjectionSet.model_validate(values)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (
            {
                "bm25_rank": None,
                "bm25_score": None,
                "vector_rank": None,
                "vector_score": None,
            },
            "at least one branch",
        ),
        ({"bm25_score": None}, "BM25 rank and score"),
        ({"vector_score": None}, "vector rank"),
        (
            {
                "bm25_rank": None,
                "bm25_score": None,
                "vector_rank": 1,
                "vector_score": 0.5,
                "bm25_highlight": "match",
            },
            "highlight requires",
        ),
    ],
)
def test_fused_candidate_requires_consistent_branch_fields(
    update: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "rank": 1,
        "rrf_score": 1 / 61,
        "chunk": chunk("a").model_dump(),
        "bm25_rank": 1,
        "bm25_score": 1.0,
        "bm25_highlight": None,
        "vector_rank": 1,
        "vector_score": 0.5,
    }
    values.update(update)

    with pytest.raises(ValidationError, match=message):
        FusedRetrievalCandidate.model_validate(values)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("bm25_space", "BM25 provenance cannot carry"),
        ("missing_vector", "requires vector provenance"),
        ("wrong_reason", "degradation reason disagree"),
        ("bm25_branch", "BM25 provenance"),
        ("vector_branch", "vector provenance"),
        ("vector_space", "vector provenance requires"),
        ("provenance_manifest", "one chunk manifest"),
        ("overflow", "Top 50"),
        ("rank", "fused ranks"),
        ("duplicate_chunk", "repeat a chunk"),
        ("duplicate_bm25_rank", "repeat a BM25 rank"),
        ("duplicate_vector_rank", "repeat a vector rank"),
        ("bm25_only_vector", "BM25-only retrieval cannot"),
        ("rrf_score", "score does not match"),
        ("rrf_order", "deterministic RRF order"),
    ],
)
def test_hybrid_result_enforces_mode_and_provenance_consistency(
    context_factory: Callable[..., ProjectExecutionContext],
    mutation: str,
    message: str,
) -> None:
    request = retrieval_request(context_factory)
    bm25_result = recall_result(
        request.plan,
        RecallBranch.BM25,
        (RecallHit(chunk=chunk("a"), rank=1, score=1.0),),
    )
    vector_result = recall_result(request.plan, RecallBranch.VECTOR, ())
    valid = asyncio.run(
        kernel(
            ScriptedQueryEmbedding([embedding_result()]),
            ScriptedBm25Recall([bm25_result]),
            ScriptedVectorRecall([vector_result]),
        ).retrieve(request)
    )
    values = valid.model_dump()
    if mutation == "bm25_space":
        cast(dict[str, object], values["bm25_provenance"])["embedding_space_fingerprint"] = (
            EMBEDDING_SPACE.model_dump()
        )
    elif mutation == "missing_vector":
        values["vector_provenance"] = None
    elif mutation == "wrong_reason":
        values["vector_degradation_reason"] = "VECTOR_RECALL_UNAVAILABLE"
    elif mutation == "bm25_branch":
        cast(dict[str, object], values["bm25_provenance"])["branch"] = "VECTOR"
    elif mutation == "vector_branch":
        cast(dict[str, object], values["vector_provenance"])["branch"] = "BM25"
    elif mutation == "vector_space":
        cast(dict[str, object], values["vector_provenance"])["embedding_space_fingerprint"] = None
    elif mutation == "provenance_manifest":
        cast(dict[str, object], values["vector_provenance"])["chunk_manifest_hash"] = "9" * 64
    elif mutation == "overflow":
        values["candidates"] = [
            FusedRetrievalCandidate(
                rank=rank,
                rrf_score=1 / (60 + rank),
                chunk=chunk(f"overflow-{rank}"),
                bm25_rank=rank,
                bm25_score=float(52 - rank),
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump()
            for rank in range(1, 52)
        ]
    elif mutation == "rank":
        cast(list[dict[str, object]], values["candidates"])[0]["rank"] = 2
    elif mutation == "duplicate_chunk":
        values["candidates"] = [
            FusedRetrievalCandidate(
                rank=1,
                rrf_score=1 / 61,
                chunk=chunk("a"),
                bm25_rank=1,
                bm25_score=1.0,
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump(),
            FusedRetrievalCandidate(
                rank=2,
                rrf_score=1 / 62,
                chunk=chunk("a"),
                bm25_rank=2,
                bm25_score=0.5,
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump(),
        ]
    elif mutation == "duplicate_bm25_rank":
        values["candidates"] = [
            FusedRetrievalCandidate(
                rank=1,
                rrf_score=1 / 61,
                chunk=chunk("a"),
                bm25_rank=1,
                bm25_score=1.0,
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump(),
            FusedRetrievalCandidate(
                rank=2,
                rrf_score=1 / 61,
                chunk=chunk("b"),
                bm25_rank=1,
                bm25_score=0.5,
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump(),
        ]
    elif mutation == "duplicate_vector_rank":
        values["candidates"] = [
            FusedRetrievalCandidate(
                rank=1,
                rrf_score=1 / 61,
                chunk=chunk("a"),
                bm25_rank=None,
                bm25_score=None,
                bm25_highlight=None,
                vector_rank=1,
                vector_score=0.5,
            ).model_dump(),
            FusedRetrievalCandidate(
                rank=2,
                rrf_score=1 / 61,
                chunk=chunk("b"),
                bm25_rank=None,
                bm25_score=None,
                bm25_highlight=None,
                vector_rank=1,
                vector_score=0.4,
            ).model_dump(),
        ]
    elif mutation == "bm25_only_vector":
        values["execution_mode"] = "BM25_ONLY"
        values["vector_degradation_reason"] = "VECTOR_RECALL_UNAVAILABLE"
        values["vector_provenance"] = None
        candidate_values = cast(list[dict[str, object]], values["candidates"])[0]
        candidate_values["vector_rank"] = 1
        candidate_values["vector_score"] = 0.5
    elif mutation == "rrf_score":
        cast(list[dict[str, object]], values["candidates"])[0]["rrf_score"] = 0.9
    else:
        values["candidates"] = [
            FusedRetrievalCandidate(
                rank=1,
                rrf_score=1 / 62,
                chunk=chunk("b"),
                bm25_rank=2,
                bm25_score=1.0,
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump(),
            FusedRetrievalCandidate(
                rank=2,
                rrf_score=1 / 61,
                chunk=chunk("a"),
                bm25_rank=1,
                bm25_score=0.5,
                bm25_highlight=None,
                vector_rank=None,
                vector_score=None,
            ).model_dump(),
        ]

    with pytest.raises(ValidationError, match=message):
        HybridRetrievalResult.model_validate(values)


def test_recall_provenance_retains_branch_identity() -> None:
    provenance = RecallProvenance(
        branch=RecallBranch.BM25,
        projection_watermark="watermark",
        chunk_manifest_hash=MANIFEST_HASH,
        projection_configuration_fingerprint=BM25_CONFIGURATION,
        embedding_space_fingerprint=None,
    )

    assert provenance.branch is RecallBranch.BM25
