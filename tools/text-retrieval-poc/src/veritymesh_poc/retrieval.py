from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
import math
import re
from typing import Iterable, Protocol

from .domain import (
    ContractError,
    EmbeddingSpace,
    IndexedChunk,
    QueryCase,
    SearchHit,
    SearchScope,
)
from .embeddings import EmbeddingAdapter, ProviderError
from .rerankers import RRFOnlyReranker, Reranker


class ServingEngine(Protocol):
    name: str

    def stage(self, items: list[IndexedChunk], idempotency_key: str) -> None: ...

    def lexical_search(self, query: str, scope: SearchScope, top_k: int) -> list[SearchHit]: ...

    def vector_search(
        self,
        vector: tuple[float, ...],
        space: EmbeddingSpace,
        scope: SearchScope,
        top_k: int,
    ) -> list[SearchHit]: ...


@dataclass(frozen=True)
class RetrieverConfig:
    bm25_top_k: int = 50
    vector_top_k: int = 50
    rrf_k: int = 60
    rrf_top_k: int = 50
    final_top_k: int = 10


class HybridRetriever:
    def __init__(
        self,
        engine: ServingEngine,
        embedder: EmbeddingAdapter,
        reranker: Reranker | None = None,
        config: RetrieverConfig | None = None,
        allow_vector_fallback: bool = True,
    ):
        self.engine = engine
        self.embedder = embedder
        self.reranker = reranker or RRFOnlyReranker()
        self.config = config or RetrieverConfig()
        self.allow_vector_fallback = allow_vector_fallback

    def search(self, query: QueryCase, *, configuration_id: str, now: str | None = None) -> list[SearchHit]:
        scope = SearchScope(
            project_id=query.project_id,
            project_version=query.project_version,
            locale=query.locale,
            allowed_access_segments=query.allowed_access_segments,
            knowledge_release_id=query.knowledge_release_id,
            configuration_id=configuration_id,
            now=now,
        )
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="retrieval-recall") as executor:
            lexical_future = executor.submit(
                self.engine.lexical_search,
                query.text,
                scope,
                self.config.bm25_top_k,
            )
            embedding_future = executor.submit(self.embedder.embed_queries, [query.text])
            dense_future = None
            try:
                query_batch = embedding_future.result()
                dense_future = executor.submit(
                    self.engine.vector_search,
                    query_batch.vectors[0],
                    query_batch.space,
                    scope,
                    self.config.vector_top_k,
                )
            except (ProviderError, ContractError, RuntimeError, TimeoutError):
                if not self.allow_vector_fallback:
                    raise
            lexical = lexical_future.result()
            if dense_future is None:
                dense = []
            else:
                try:
                    dense = dense_future.result()
                except (ProviderError, ContractError, RuntimeError, TimeoutError):
                    if not self.allow_vector_fallback:
                        raise
                    dense = []
        fused = reciprocal_rank_fusion(lexical, dense, k=self.config.rrf_k, top_k=self.config.rrf_top_k)
        return self.reranker.rerank(query.text, fused, self.config.final_top_k)


def reciprocal_rank_fusion(
    lexical: list[SearchHit],
    dense: list[SearchHit],
    *,
    k: int = 60,
    top_k: int = 50,
) -> list[SearchHit]:
    if k <= 0 or top_k <= 0:
        raise ContractError("RRF k and top_k must be positive")
    aggregate: dict[str, dict[str, object]] = {}
    for source, hits in (("bm25", lexical), ("vector", dense)):
        for rank, hit in enumerate(hits, start=1):
            record = aggregate.setdefault(
                hit.chunk.chunk_id,
                {"chunk": hit.chunk, "score": 0.0, "lexical": None, "vector": None},
            )
            record["score"] = float(record["score"]) + 1.0 / (k + rank)
            record[source if source == "vector" else "lexical"] = hit.score
    fused = [
        SearchHit(
            chunk=record["chunk"],  # type: ignore[arg-type]
            score=float(record["score"]),
            rank=0,
            source="rrf",
            lexical_score=record["lexical"],  # type: ignore[arg-type]
            vector_score=record["vector"],  # type: ignore[arg-type]
        )
        for record in aggregate.values()
    ]
    fused.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
    return [replace(hit, rank=index + 1) for index, hit in enumerate(fused[:top_k])]


@dataclass(frozen=True)
class BindingKey:
    project_id: str
    project_version: str
    locale: str
    access_segment: str


class ReleaseRouter:
    """In-memory model of the control-plane atomic active-binding pointer."""

    def __init__(self) -> None:
        self._active: dict[BindingKey, str] = {}
        self._idempotency: dict[str, str] = {}

    def activate(self, binding: BindingKey, release_id: str, idempotency_key: str) -> None:
        payload = f"{binding!r}\x1f{release_id}"
        self._idempotent("activate", idempotency_key, payload)
        self._active[binding] = release_id

    def resolve(self, binding: BindingKey) -> str:
        try:
            return self._active[binding]
        except KeyError as error:
            raise ContractError(f"no active release for binding: {binding}") from error

    def _idempotent(self, operation: str, key: str, payload: str) -> None:
        signature = sha256(f"{operation}\x1f{payload}".encode("utf-8")).hexdigest()
        prior = self._idempotency.get(key)
        if prior is not None and prior != signature:
            raise ContractError(f"idempotency key reused with a different {operation} payload")
        self._idempotency[key] = signature


class InMemoryServingEngine:
    """Reference engine for deterministic contract testing, not a product benchmark."""

    name = "in_memory_contract"
    _tokens = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]", re.UNICODE)

    def __init__(self) -> None:
        self._items: dict[str, IndexedChunk] = {}
        self._idempotency: dict[str, str] = {}
        self._revoked_revisions: set[str] = set()
        self._revoked_chunks: set[str] = set()

    def stage(self, items: list[IndexedChunk], idempotency_key: str) -> None:
        if not items:
            raise ContractError("cannot stage an empty chunk set")
        payload = "\n".join(
            sorted(
                f"{item.chunk.chunk_id}:{item.embedding_space_fingerprint}:{item.configuration_id}"
                for item in items
            )
        )
        self._idempotent("stage", idempotency_key, payload)
        for item in items:
            if len(item.vector) == 0:
                raise ContractError("cannot stage an empty embedding vector")
            if not item.embedding_space_fingerprint:
                raise ContractError("staged item has no embedding-space fingerprint")
            self._items[item.chunk.chunk_id] = item

    def revoke_revision(self, knowledge_revision_id: str, idempotency_key: str) -> None:
        self._idempotent("revoke_revision", idempotency_key, knowledge_revision_id)
        self._revoked_revisions.add(knowledge_revision_id)

    def revoke_chunk(self, chunk_id: str, idempotency_key: str) -> None:
        self._idempotent("revoke_chunk", idempotency_key, chunk_id)
        self._revoked_chunks.add(chunk_id)

    def delete_document(self, document_id: str, idempotency_key: str) -> None:
        self._idempotent("delete_document", idempotency_key, document_id)
        for chunk_id in [
            item.chunk.chunk_id for item in self._items.values() if item.chunk.document_id == document_id
        ]:
            del self._items[chunk_id]

    def lexical_search(self, query: str, scope: SearchScope, top_k: int) -> list[SearchHit]:
        candidates = self._eligible(scope)
        scores = _bm25(query, [item.chunk.search_text for item in candidates], self._tokens)
        hits = [
            SearchHit(item.chunk, score, 0, "bm25", lexical_score=score)
            for item, score in zip(candidates, scores, strict=True)
            if score > 0.0
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return [replace(hit, rank=index + 1) for index, hit in enumerate(hits[:top_k])]

    def vector_search(
        self,
        vector: tuple[float, ...],
        space: EmbeddingSpace,
        scope: SearchScope,
        top_k: int,
    ) -> list[SearchHit]:
        if len(vector) != space.dimension:
            raise ContractError("query vector dimension does not match its embedding space")
        candidates = self._eligible(scope)
        expected = space.fingerprint
        mismatches = [
            item.chunk.chunk_id
            for item in candidates
            if item.embedding_space_fingerprint != expected or len(item.vector) != len(vector)
        ]
        if mismatches:
            raise ContractError(
                "mixed or incompatible query/document vector spaces in serving scope: "
                + ", ".join(mismatches[:3])
            )
        hits = [
            SearchHit(item.chunk, _cosine(vector, item.vector), 0, "vector", vector_score=_cosine(vector, item.vector))
            for item in candidates
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return [replace(hit, rank=index + 1) for index, hit in enumerate(hits[:top_k])]

    def all_items(self) -> list[IndexedChunk]:
        return list(self._items.values())

    def _eligible(self, scope: SearchScope) -> list[IndexedChunk]:
        result = []
        for item in self._items.values():
            chunk = item.chunk
            if item.configuration_id != scope.configuration_id:
                continue
            if chunk.project_id != scope.project_id:
                continue
            if chunk.project_version != scope.project_version:
                continue
            if chunk.locale != scope.locale:
                continue
            if chunk.knowledge_release_id != scope.knowledge_release_id:
                continue
            if chunk.access_segment not in scope.allowed_access_segments:
                continue
            if chunk.knowledge_revision_id in self._revoked_revisions or chunk.chunk_id in self._revoked_chunks:
                continue
            if scope.now and chunk.effective_from and scope.now < chunk.effective_from:
                continue
            if scope.now and chunk.effective_to and scope.now > chunk.effective_to:
                continue
            result.append(item)
        return result

    def _idempotent(self, operation: str, key: str, payload: str) -> None:
        signature = sha256(f"{operation}\x1f{payload}".encode("utf-8")).hexdigest()
        prior = self._idempotency.get(key)
        if prior is not None and prior != signature:
            raise ContractError(f"idempotency key reused with a different {operation} payload")
        self._idempotency[key] = signature


def _bm25(query: str, documents: list[str], token_pattern: re.Pattern[str]) -> list[float]:
    query_terms = [token.lower() for token in token_pattern.findall(query)]
    if not query_terms or not documents:
        return [0.0] * len(documents)
    terms_by_document = [[token.lower() for token in token_pattern.findall(text)] for text in documents]
    document_frequency: Counter[str] = Counter()
    for terms in terms_by_document:
        document_frequency.update(set(terms))
    average_length = sum(len(terms) for terms in terms_by_document) / len(terms_by_document)
    k1 = 1.2
    b = 0.75
    scores: list[float] = []
    for terms in terms_by_document:
        frequencies = Counter(terms)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            inverse_document_frequency = math.log(
                1 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * len(terms) / max(1.0, average_length))
            score += inverse_document_frequency * frequency * (k1 + 1) / denominator
        scores.append(score)
    return scores


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
