import asyncio
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from conftest import NOW
from veritymesh_assistant_runtime.evidence import (
    EvidenceRevocationCheckRequest,
    EvidenceRevocationCheckResult,
)
from veritymesh_assistant_runtime.execution_context import (
    AccessSegment,
    ExecutionContextGuard,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.query_planning import (
    DeterministicProjectQueryPlanner,
    ProjectQueryPlan,
    QueryPlanningRequest,
)
from veritymesh_assistant_runtime.reranking import RerankerRequest, RerankerResult
from veritymesh_assistant_runtime.retrieval import (
    Bm25RecallPort,
    Bm25RecallRequest,
    EmbeddingSpaceFingerprint,
    HybridRetrievalKernel,
    HybridRetrievalRequest,
    QueryEmbeddingPort,
    QueryEmbeddingRequest,
    QueryEmbeddingResult,
    RecallBranch,
    RecallHit,
    RecallProjectionExpectation,
    RecallResult,
    RetrievalChunk,
    RetrievalProjectionSet,
    VectorRecallPort,
    VectorRecallRequest,
)
from veritymesh_assistant_runtime.revocation import (
    RevocationClearedExecutionContext,
    RevocationScope,
)

MANIFEST_HASH = "1" * 64
BM25_CONFIGURATION = "2" * 64
VECTOR_CONFIGURATION = "3" * 64
EMBEDDING_FINGERPRINT = "4" * 64
CONTENT_HASH = "5" * 64

EMBEDDING_SPACE = EmbeddingSpaceFingerprint(
    fingerprint=EMBEDDING_FINGERPRINT,
    dimension=2,
)


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


def cleared_context(
    context_factory: Callable[..., ProjectExecutionContext],
) -> RevocationClearedExecutionContext:
    guarded = ExecutionContextGuard(lambda: NOW).validate(context_factory())
    return RevocationClearedExecutionContext(
        guarded_context=guarded,
        revocation_scope=RevocationScope.from_context(guarded.context),
        revocation_snapshot_version="revocation-snapshot-7",
        revocation_checked_at=NOW,
        revocation_valid_until=NOW + timedelta(seconds=10),
    )


def query_plan(context: RevocationClearedExecutionContext) -> ProjectQueryPlan:
    return asyncio.run(
        DeterministicProjectQueryPlanner().plan(
            QueryPlanningRequest(context=context, original_query="API 错误怎么处理?")
        )
    )


def projection_set() -> RetrievalProjectionSet:
    return RetrievalProjectionSet(
        knowledge_release_id="release-1",
        bm25=RecallProjectionExpectation(
            projection_watermark="bm25-watermark-1",
            chunk_manifest_hash=MANIFEST_HASH,
            projection_configuration_fingerprint=BM25_CONFIGURATION,
        ),
        vector=RecallProjectionExpectation(
            projection_watermark="vector-watermark-1",
            chunk_manifest_hash=MANIFEST_HASH,
            projection_configuration_fingerprint=VECTOR_CONFIGURATION,
        ),
        embedding_space_fingerprint=EMBEDDING_SPACE,
    )


def retrieval_request(
    context_factory: Callable[..., ProjectExecutionContext],
) -> HybridRetrievalRequest:
    context = cleared_context(context_factory)
    return HybridRetrievalRequest(
        context=context,
        plan=query_plan(context),
        projections=projection_set(),
    )


def chunk(
    chunk_id: str,
    *,
    title: str | None = None,
    citation_url: str | None = None,
    effective_from: datetime | None = NOW - timedelta(days=1),
    effective_to: datetime | None = NOW + timedelta(days=1),
) -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=chunk_id,
        document_id=f"document-{chunk_id}",
        knowledge_revision_id=f"revision-{chunk_id}",
        knowledge_space_id="space-1",
        project_id="project-1",
        project_version="1.0.0",
        locale="zh-CN",
        access_segment=AccessSegment.PROJECT_AUTHORIZED,
        knowledge_release_id="release-1",
        content_hash=CONTENT_HASH,
        chunk_manifest_hash=MANIFEST_HASH,
        title=title or f"Title {chunk_id}",
        section="API",
        chunk_text=f"Chunk text {chunk_id}",
        citation_url=citation_url or f"/citations/{chunk_id}",
        start_char=0,
        end_char=10,
        effective_from=effective_from,
        effective_to=effective_to,
    )


def recall_result(
    plan: ProjectQueryPlan,
    branch: RecallBranch,
    hits: tuple[RecallHit, ...],
) -> RecallResult:
    projection = projection_set().bm25 if branch is RecallBranch.BM25 else projection_set().vector
    return RecallResult(
        schema_version="1.0",
        branch=branch,
        filters=plan.filters,
        message_execution_id=plan.message_execution_id,
        projection_watermark=projection.projection_watermark,
        chunk_manifest_hash=projection.chunk_manifest_hash,
        projection_configuration_fingerprint=(projection.projection_configuration_fingerprint),
        embedding_space_fingerprint=(EMBEDDING_SPACE if branch is RecallBranch.VECTOR else None),
        hits=hits,
    )


def embedding_result() -> QueryEmbeddingResult:
    return QueryEmbeddingResult(
        vector=(1.0, 0.0),
        embedding_space_fingerprint=EMBEDDING_SPACE,
    )


def kernel(
    embedding: QueryEmbeddingPort,
    bm25: Bm25RecallPort,
    vector: VectorRecallPort,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
) -> HybridRetrievalKernel:
    return HybridRetrievalKernel(
        query_embedding=embedding,
        bm25_recall=bm25,
        vector_recall=vector,
        clock=clock,
    )


class ScriptedQueryEmbedding:
    """Records query-embedding calls and replays results or failures."""

    def __init__(self, outcomes: Iterable[QueryEmbeddingResult | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[QueryEmbeddingRequest] = []

    async def embed_query(self, request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted query embedding has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedBm25Recall:
    """Records BM25 calls and replays results or failures."""

    def __init__(self, outcomes: Iterable[RecallResult | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[Bm25RecallRequest] = []

    async def recall(self, request: Bm25RecallRequest) -> RecallResult:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted BM25 recall has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedVectorRecall:
    """Records vector calls and replays results or failures."""

    def __init__(self, outcomes: Iterable[RecallResult | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[VectorRecallRequest] = []

    async def recall(self, request: VectorRecallRequest) -> RecallResult:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted vector recall has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedReranker:
    """Records reranking calls and replays configured results or failures."""

    def __init__(self, outcomes: Iterable[RerankerResult | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[RerankerRequest] = []

    async def rerank(self, request: RerankerRequest) -> RerankerResult:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted reranker has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedEvidenceRevocationChecker:
    """Records content-revocation calls and replays results or failures."""

    def __init__(self, outcomes: Iterable[EvidenceRevocationCheckResult | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[EvidenceRevocationCheckRequest] = []

    async def check(
        self,
        request: EvidenceRevocationCheckRequest,
    ) -> EvidenceRevocationCheckResult:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted evidence revocation checker has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
