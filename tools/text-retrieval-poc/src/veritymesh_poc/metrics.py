from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from statistics import fmean
from typing import Sequence

from .domain import QueryCase, SearchHit


@dataclass(frozen=True)
class QueryMeasurement:
    query_id: str
    relevant_documents: dict[str, int]
    retrieved_document_ids: tuple[str, ...]
    latency_ms: float

    @classmethod
    def from_hits(cls, query: QueryCase, hits: Sequence[SearchHit], latency_ms: float) -> "QueryMeasurement":
        unique_document_ids: list[str] = []
        seen: set[str] = set()
        for hit in hits:
            if hit.chunk.document_id not in seen:
                seen.add(hit.chunk.document_id)
                unique_document_ids.append(hit.chunk.document_id)
        return cls(
            query_id=query.query_id,
            relevant_documents=dict(query.relevant_documents),
            retrieved_document_ids=tuple(unique_document_ids),
            latency_ms=latency_ms,
        )


@dataclass(frozen=True)
class RetrievalMetrics:
    query_count: int
    recall_at_10: float
    ndcg_at_10: float
    mrr_at_10: float
    top3_valid_evidence_rate: float
    search_p50_ms: float
    search_p95_ms: float
    search_max_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def evaluate(measurements: Sequence[QueryMeasurement], *, cutoff: int = 10) -> RetrievalMetrics:
    if not measurements:
        raise ValueError("cannot evaluate an empty query set")
    recalls: list[float] = []
    ndcgs: list[float] = []
    mrrs: list[float] = []
    hits_at_three: list[float] = []
    latencies: list[float] = []
    for measurement in measurements:
        relevant = {document_id: grade for document_id, grade in measurement.relevant_documents.items() if grade > 0}
        if not relevant:
            raise ValueError(f"query {measurement.query_id} has no positive relevance judgement")
        retrieved = measurement.retrieved_document_ids[:cutoff]
        retrieved_relevant = {document_id for document_id in retrieved if document_id in relevant}
        recalls.append(len(retrieved_relevant) / len(relevant))
        ndcgs.append(_ndcg(retrieved, relevant, cutoff))
        mrrs.append(_mrr(retrieved, relevant))
        hits_at_three.append(1.0 if any(document_id in relevant for document_id in retrieved[:3]) else 0.0)
        latencies.append(measurement.latency_ms)
    return RetrievalMetrics(
        query_count=len(measurements),
        recall_at_10=fmean(recalls),
        ndcg_at_10=fmean(ndcgs),
        mrr_at_10=fmean(mrrs),
        top3_valid_evidence_rate=fmean(hits_at_three),
        search_p50_ms=_percentile(latencies, 50),
        search_p95_ms=_percentile(latencies, 95),
        search_max_ms=max(latencies),
    )


def _ndcg(retrieved: Sequence[str], relevant: dict[str, int], cutoff: int) -> float:
    actual = 0.0
    for position, document_id in enumerate(retrieved[:cutoff], start=1):
        grade = relevant.get(document_id, 0)
        actual += (2**grade - 1) / math.log2(position + 1)
    ideal_grades = sorted(relevant.values(), reverse=True)[:cutoff]
    ideal = sum((2**grade - 1) / math.log2(position + 1) for position, grade in enumerate(ideal_grades, start=1))
    return actual / ideal if ideal else 0.0


def _mrr(retrieved: Sequence[str], relevant: dict[str, int]) -> float:
    for position, document_id in enumerate(retrieved, start=1):
        if document_id in relevant:
            return 1.0 / position
    return 0.0


def _percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
