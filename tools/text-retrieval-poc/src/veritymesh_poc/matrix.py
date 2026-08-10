from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Protocol

from .metrics import RetrievalMetrics


PRIMARY_ENGINES = ("aliyun_elasticsearch", "aliyun_opensearch_vector")
EMBEDDING_CANDIDATES = ("qwen3_7_text_embedding", "text_embedding_v4")
CHUNK_CHALLENGERS = ("fixed_recursive", "semantic_boundary")
RERANKER_CANDIDATES = ("qwen3_rerank", "gte_rerank_v2")
MIN_QUALITY_GAIN = 0.01


@dataclass(frozen=True)
class MatrixCandidate:
    phase: int
    engine: str
    embedding: str
    chunker: str
    reranker: str

    @property
    def configuration_id(self) -> str:
        return "-".join(
            (
                f"p{self.phase}",
                _slug(self.engine),
                _slug(self.embedding),
                _slug(self.chunker),
                _slug(self.reranker),
            )
        )

    def to_dict(self) -> dict[str, str | int]:
        return {
            "phase": self.phase,
            "configuration_id": self.configuration_id,
            "engine": self.engine,
            "embedding": self.embedding,
            "chunker": self.chunker,
            "reranker": self.reranker,
        }


def phase_one() -> list[MatrixCandidate]:
    return [
        MatrixCandidate(1, engine, embedding, "structure_aware", "rrf_only")
        for engine in PRIMARY_ENGINES
        for embedding in EMBEDDING_CANDIDATES
    ]


def phase_two(winning_embedding: str) -> list[MatrixCandidate]:
    if winning_embedding not in EMBEDDING_CANDIDATES:
        raise ValueError(f"unknown phase-two embedding: {winning_embedding}")
    return [
        MatrixCandidate(2, engine, winning_embedding, "structure_aware", reranker)
        for engine in PRIMARY_ENGINES
        for reranker in RERANKER_CANDIDATES
    ]


def phase_three(winning_embedding: str) -> list[MatrixCandidate]:
    if winning_embedding not in EMBEDDING_CANDIDATES:
        raise ValueError(f"unknown phase-three embedding: {winning_embedding}")
    return [
        MatrixCandidate(3, engine, winning_embedding, chunker, "rrf_only")
        for engine in PRIMARY_ENGINES
        for chunker in CHUNK_CHALLENGERS
    ]


def phase_four(winning_embedding: str, winning_chunker: str, winning_reranker: str) -> list[MatrixCandidate]:
    if (
        winning_embedding not in EMBEDDING_CANDIDATES
        or winning_chunker not in CHUNK_CHALLENGERS
        or winning_reranker not in RERANKER_CANDIDATES
    ):
        return []
    return [
        MatrixCandidate(4, engine, winning_embedding, winning_chunker, winning_reranker)
        for engine in PRIMARY_ENGINES
    ]


def planned_matrix(
    winning_embedding: str | None = None,
    winning_chunker: str | None = None,
    winning_reranker: str | None = None,
) -> list[MatrixCandidate]:
    plan = phase_one()
    if winning_embedding:
        plan.extend(phase_two(winning_embedding))
        plan.extend(phase_three(winning_embedding))
    if winning_embedding and winning_chunker and winning_reranker:
        plan.extend(phase_four(winning_embedding, winning_chunker, winning_reranker))
    return plan


class MeasuredConfiguration(Protocol):
    candidate: MatrixCandidate
    metrics: RetrievalMetrics | None
    error: str | None


def select_embedding(records: Iterable[MeasuredConfiguration]) -> str:
    grouped: dict[str, list[RetrievalMetrics]] = {name: [] for name in EMBEDDING_CANDIDATES}
    for record in records:
        if record.candidate.phase == 1 and record.metrics is not None and record.error is None:
            grouped.setdefault(record.candidate.embedding, []).append(record.metrics)
    viable = {name: metrics for name, metrics in grouped.items() if metrics}
    if not viable:
        raise ValueError("phase one produced no successful configuration; cannot select an embedding")
    # Quality first. Latency only breaks an otherwise material tie; avoid rewarding a fast but weak retriever.
    return max(
        viable,
        key=lambda name: (
            fmean(metric.recall_at_10 for metric in viable[name]),
            fmean(metric.top3_valid_evidence_rate for metric in viable[name]),
            fmean(metric.ndcg_at_10 for metric in viable[name]),
            fmean(metric.mrr_at_10 for metric in viable[name]),
            -fmean(metric.search_p95_ms for metric in viable[name]),
            1 if name == "qwen3_7_text_embedding" else 0,
        ),
    )


def select_reranker(
    records: Iterable[MeasuredConfiguration],
    baseline_records: Iterable[MeasuredConfiguration],
) -> str | None:
    grouped: dict[str, list[RetrievalMetrics]] = {name: [] for name in RERANKER_CANDIDATES}
    for record in records:
        if record.candidate.phase == 2 and record.metrics is not None and record.error is None:
            grouped.setdefault(record.candidate.reranker, []).append(record.metrics)
    viable = {name: metrics for name, metrics in grouped.items() if metrics}
    if not viable:
        return None
    baseline = _summary(baseline_records)
    if baseline is None:
        return None
    winner = max(
        viable,
        key=lambda name: (
            fmean(metric.top3_valid_evidence_rate for metric in viable[name]),
            fmean(metric.ndcg_at_10 for metric in viable[name]),
            fmean(metric.mrr_at_10 for metric in viable[name]),
            fmean(metric.recall_at_10 for metric in viable[name]),
            -fmean(metric.search_p95_ms for metric in viable[name]),
            1 if name == "qwen3_rerank" else 0,
        ),
    )
    return winner if _materially_beats(_summary_from_metrics(viable[winner]), baseline) else None


def select_chunk_challenger(
    records: Iterable[MeasuredConfiguration],
    baseline_records: Iterable[MeasuredConfiguration],
) -> str | None:
    candidates: dict[str, list[RetrievalMetrics]] = {name: [] for name in CHUNK_CHALLENGERS}
    for record in records:
        if record.candidate.phase == 3 and record.metrics is not None and record.error is None:
            candidates.setdefault(record.candidate.chunker, []).append(record.metrics)
    viable = {name: metrics for name, metrics in candidates.items() if metrics}
    if not viable:
        return None
    baseline = _summary(baseline_records)
    if baseline is None:
        return None
    winner = max(
        viable,
        key=lambda name: (
            fmean(metric.recall_at_10 for metric in viable[name]),
            fmean(metric.ndcg_at_10 for metric in viable[name]),
            -fmean(metric.search_p95_ms for metric in viable[name]),
        ),
    )
    return winner if _materially_beats(_summary_from_metrics(viable[winner]), baseline) else None


def _summary(records: Iterable[MeasuredConfiguration]) -> dict[str, float] | None:
    metrics = [
        record.metrics
        for record in records
        if record.metrics is not None and record.error is None
    ]
    return _summary_from_metrics(metrics) if metrics else None


def _summary_from_metrics(metrics: Iterable[RetrievalMetrics]) -> dict[str, float]:
    values = list(metrics)
    return {
        "recall": fmean(metric.recall_at_10 for metric in values),
        "top3": fmean(metric.top3_valid_evidence_rate for metric in values),
        "ndcg": fmean(metric.ndcg_at_10 for metric in values),
        "mrr": fmean(metric.mrr_at_10 for metric in values),
    }


def _materially_beats(candidate: dict[str, float], baseline: dict[str, float]) -> bool:
    no_regression = (
        candidate["recall"] >= baseline["recall"]
        and candidate["top3"] >= baseline["top3"]
    )
    material_gain = any(
        candidate[metric] >= baseline[metric] + MIN_QUALITY_GAIN
        for metric in ("top3", "ndcg", "mrr")
    )
    return no_regression and material_gain


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")
