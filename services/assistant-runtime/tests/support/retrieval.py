from collections import deque
from collections.abc import Iterable

from veritymesh_assistant_runtime.retrieval import (
    Bm25RecallRequest,
    QueryEmbeddingRequest,
    QueryEmbeddingResult,
    RecallResult,
    VectorRecallRequest,
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
