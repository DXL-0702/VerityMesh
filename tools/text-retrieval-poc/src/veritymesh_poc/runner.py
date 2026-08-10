from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import time
from typing import Callable, Iterable

from .chunking import FixedRecursiveChunker, SemanticBoundaryChunker, StructureAwareChunker
from .domain import Document, EvidenceLevel, IndexedChunk, QueryCase
from .embeddings import EmbeddingAdapter, DeterministicHashEmbedding
from .gates import GateResult, run_in_memory_contract_gates
from .matrix import MatrixCandidate
from .metrics import QueryMeasurement, RetrievalMetrics, evaluate
from .rerankers import LexicalOverlapReranker, RRFOnlyReranker, Reranker
from .retrieval import HybridRetriever, InMemoryServingEngine, ServingEngine
from .tokenization import OffsetTokenizer, UnicodeRegexTokenizer


@dataclass(frozen=True)
class RunRecord:
    candidate: MatrixCandidate
    evidence_level: EvidenceLevel
    metrics: RetrievalMetrics | None
    measurements: tuple[QueryMeasurement, ...]
    indexed_document_count: int
    indexed_chunk_count: int
    embedding_space_fingerprint: str | None
    reranker_version: str | None
    tokenizer_fingerprint: str | None
    gate_results: tuple[GateResult, ...] = ()
    error: str | None = None

    @property
    def hard_gates_passed(self) -> bool:
        return bool(self.gate_results) and all(result.passed for result in self.gate_results)

    def to_dict(self) -> dict:
        return {
            "candidate": self.candidate.to_dict(),
            "evidence_level": self.evidence_level.value,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "measurements": [asdict(measurement) for measurement in self.measurements],
            "indexed_document_count": self.indexed_document_count,
            "indexed_chunk_count": self.indexed_chunk_count,
            "embedding_space_fingerprint": self.embedding_space_fingerprint,
            "reranker_version": self.reranker_version,
            "tokenizer_fingerprint": self.tokenizer_fingerprint,
            "hard_gates_passed": self.hard_gates_passed,
            "gate_results": [result.to_dict() for result in self.gate_results],
            "error": self.error,
        }


def execute_candidate(
    *,
    candidate: MatrixCandidate,
    documents: list[Document],
    queries: list[QueryCase],
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    reranker: Reranker,
    evidence_level: EvidenceLevel,
    gate_results: Iterable[GateResult] = (),
    tokenizer: OffsetTokenizer | None = None,
) -> RunRecord:
    indexed_chunk_count = 0
    try:
        tokenizer = tokenizer or UnicodeRegexTokenizer()
        indexed = _index_documents(documents, candidate, engine, embedder, tokenizer)
        indexed_chunk_count = len(indexed)
        retriever = HybridRetriever(
            engine,
            embedder,
            reranker,
            allow_vector_fallback=False,
        )
        measurements: list[QueryMeasurement] = []
        for query in queries:
            started = time.perf_counter()
            hits = retriever.search(query, configuration_id=candidate.configuration_id)
            latency_ms = (time.perf_counter() - started) * 1000.0
            measurements.append(QueryMeasurement.from_hits(query, hits, latency_ms))
        return RunRecord(
            candidate=candidate,
            evidence_level=evidence_level,
            metrics=evaluate(measurements),
            measurements=tuple(measurements),
            indexed_document_count=len({item.chunk.document_id for item in indexed}),
            indexed_chunk_count=indexed_chunk_count,
            embedding_space_fingerprint=embedder.space.fingerprint,
            reranker_version=getattr(reranker, "version", None),
            tokenizer_fingerprint=tokenizer.fingerprint,
            gate_results=tuple(gate_results),
        )
    except Exception as error:
        return RunRecord(
            candidate=candidate,
            evidence_level=evidence_level,
            metrics=None,
            measurements=(),
            indexed_document_count=0,
            indexed_chunk_count=indexed_chunk_count,
            embedding_space_fingerprint=getattr(embedder, "space", None).fingerprint if getattr(embedder, "space", None) else None,
            reranker_version=getattr(reranker, "version", None),
            tokenizer_fingerprint=tokenizer.fingerprint if tokenizer else None,
            gate_results=tuple(gate_results),
            error=f"{type(error).__name__}: {error}",
        )


def run_local_validation(documents: list[Document], queries: list[QueryCase]) -> list[RunRecord]:
    gates = tuple(run_in_memory_contract_gates())
    candidates = (
        MatrixCandidate(0, "in_memory_contract", "deterministic_hash", "structure_aware", "rrf_only"),
        MatrixCandidate(0, "in_memory_contract", "deterministic_hash", "fixed_recursive", "rrf_only"),
        MatrixCandidate(0, "in_memory_contract", "deterministic_hash", "semantic_boundary", "rrf_only"),
        MatrixCandidate(0, "in_memory_contract", "deterministic_hash", "structure_aware", "local_lexical_rerank"),
    )
    records: list[RunRecord] = []
    for candidate in candidates:
        embedder = DeterministicHashEmbedding()
        reranker: Reranker = LexicalOverlapReranker() if candidate.reranker == "local_lexical_rerank" else RRFOnlyReranker()
        records.append(
            execute_candidate(
                candidate=candidate,
                documents=documents,
                queries=queries,
                engine=InMemoryServingEngine(),
                embedder=embedder,
                reranker=reranker,
                evidence_level=EvidenceLevel.HARNESS_VALIDATION,
                gate_results=gates,
                tokenizer=UnicodeRegexTokenizer(),
            )
        )
    return records


def _index_documents(
    documents: list[Document],
    candidate: MatrixCandidate,
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    tokenizer: OffsetTokenizer,
) -> list[IndexedChunk]:
    chunker = _build_chunker(candidate.chunker, embedder, tokenizer)
    chunks = [chunk for document in documents for chunk in chunker.chunk(document)]
    if not chunks:
        raise ValueError("chunker produced no chunks")
    vectors = _embed_in_batches(embedder, [chunk.search_text for chunk in chunks])
    indexed = [
        IndexedChunk(
            chunk=chunk,
            vector=vector,
            embedding_space_fingerprint=vectors.space.fingerprint,
            configuration_id=candidate.configuration_id,
        )
        for chunk, vector in zip(chunks, vectors.vectors, strict=True)
    ]
    releases: dict[str, list[IndexedChunk]] = defaultdict(list)
    for item in indexed:
        releases[item.chunk.knowledge_release_id].append(item)
    for release_id, release_items in releases.items():
        signature = sha256(
            "\n".join(item.chunk.chunk_id for item in release_items).encode("utf-8")
        ).hexdigest()[:16]
        engine.stage(release_items, f"{candidate.configuration_id}:{release_id}:{signature}")
    return indexed


def _build_chunker(name: str, embedder: EmbeddingAdapter, tokenizer: OffsetTokenizer):
    if name == "structure_aware":
        return StructureAwareChunker(tokenizer)
    if name == "fixed_recursive":
        return FixedRecursiveChunker(tokenizer)
    if name == "semantic_boundary":
        return SemanticBoundaryChunker(embedder, tokenizer)
    raise ValueError(f"unknown chunker: {name}")


def _embed_in_batches(embedder: EmbeddingAdapter, texts: list[str], batch_size: int = 64):
    vectors = []
    space = None
    for start in range(0, len(texts), batch_size):
        batch = embedder.embed_documents(texts[start : start + batch_size])
        if space is not None and batch.space.fingerprint != space.fingerprint:
            raise ValueError("embedding adapter changed spaces within one index build")
        space = batch.space
        vectors.extend(batch.vectors)
    if space is None:
        raise ValueError("no text passed to embedding adapter")
    from .domain import EmbeddingBatch

    return EmbeddingBatch(tuple(vectors), space)
