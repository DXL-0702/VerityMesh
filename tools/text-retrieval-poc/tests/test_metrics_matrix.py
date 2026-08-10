from __future__ import annotations

from dataclasses import dataclass
import unittest

from veritymesh_poc.matrix import (
    phase_four,
    phase_one,
    phase_three,
    phase_two,
    select_chunk_challenger,
    select_embedding,
    select_reranker,
)
from veritymesh_poc.metrics import QueryMeasurement, RetrievalMetrics, evaluate


class MetricsAndMatrixTests(unittest.TestCase):
    def test_metrics_deduplicate_multiple_chunks_from_one_document(self) -> None:
        measurement = QueryMeasurement(
            query_id="q1",
            relevant_documents={"right": 2, "also-right": 1},
            retrieved_document_ids=("right", "right", "wrong", "also-right"),
            latency_ms=100.0,
        )
        metrics = evaluate([measurement])
        self.assertEqual(metrics.recall_at_10, 1.0)
        self.assertEqual(metrics.top3_valid_evidence_rate, 1.0)
        self.assertGreater(metrics.ndcg_at_10, 0.9)

    def test_joint_matrix_counts_are_deliberate_not_full_cartesian_product(self) -> None:
        self.assertEqual(len(phase_one()), 4)
        self.assertEqual(len(phase_two("qwen3_7_text_embedding")), 4)
        self.assertEqual(len(phase_three("qwen3_7_text_embedding")), 4)
        self.assertEqual(
            len(phase_four("qwen3_7_text_embedding", "semantic_boundary", "qwen3_rerank")),
            2,
        )

    def test_embedding_selection_is_quality_first(self) -> None:
        @dataclass(frozen=True)
        class Record:
            candidate: object
            metrics: RetrievalMetrics | None
            error: str | None = None

        strong = RetrievalMetrics(2, 0.95, 0.80, 0.80, 0.90, 20.0, 30.0, 30.0)
        fast_but_weak = RetrievalMetrics(2, 0.85, 0.99, 0.99, 0.99, 1.0, 2.0, 2.0)
        records = [
            Record(phase_one()[0], strong),
            Record(phase_one()[1], fast_but_weak),
            Record(phase_one()[2], strong),
            Record(phase_one()[3], fast_but_weak),
        ]
        self.assertEqual(select_embedding(records), "qwen3_7_text_embedding")

    def test_reranker_selection_is_quality_first(self) -> None:
        @dataclass(frozen=True)
        class Record:
            candidate: object
            metrics: RetrievalMetrics | None
            error: str | None = None

        baseline_metrics = RetrievalMetrics(2, 0.95, 0.85, 0.84, 0.88, 300.0, 350.0, 350.0)
        strong = RetrievalMetrics(2, 0.95, 0.92, 0.91, 0.95, 400.0, 450.0, 450.0)
        fast_but_weak = RetrievalMetrics(2, 0.95, 0.84, 0.82, 0.86, 100.0, 120.0, 120.0)
        candidates = phase_two("qwen3_7_text_embedding")
        baseline_candidates = [candidate for candidate in phase_one() if candidate.embedding == "qwen3_7_text_embedding"]
        records = [
            Record(candidates[0], strong),
            Record(candidates[1], fast_but_weak),
            Record(candidates[2], strong),
            Record(candidates[3], fast_but_weak),
        ]
        baseline = [Record(candidate, baseline_metrics) for candidate in baseline_candidates]
        self.assertEqual(select_reranker(records, baseline), "qwen3_rerank")

    def test_reranker_is_not_selected_when_it_does_not_beat_rrf(self) -> None:
        @dataclass(frozen=True)
        class Record:
            candidate: object
            metrics: RetrievalMetrics | None
            error: str | None = None

        baseline_metrics = RetrievalMetrics(2, 0.95, 0.90, 0.90, 0.92, 200.0, 220.0, 220.0)
        weak = RetrievalMetrics(2, 0.95, 0.89, 0.89, 0.91, 300.0, 320.0, 320.0)
        baseline = [
            Record(candidate, baseline_metrics)
            for candidate in phase_one()
            if candidate.embedding == "qwen3_7_text_embedding"
        ]
        records = [Record(candidate, weak) for candidate in phase_two("qwen3_7_text_embedding")]
        self.assertIsNone(select_reranker(records, baseline))

    def test_chunk_challenger_must_materially_beat_structure_aware(self) -> None:
        @dataclass(frozen=True)
        class Record:
            candidate: object
            metrics: RetrievalMetrics | None
            error: str | None = None

        baseline_metrics = RetrievalMetrics(2, 0.95, 0.86, 0.85, 0.90, 200.0, 220.0, 220.0)
        semantic_gain = RetrievalMetrics(2, 0.95, 0.89, 0.88, 0.92, 210.0, 230.0, 230.0)
        fixed_weak = RetrievalMetrics(2, 0.94, 0.84, 0.84, 0.89, 180.0, 200.0, 200.0)
        baseline = [
            Record(candidate, baseline_metrics)
            for candidate in phase_one()
            if candidate.embedding == "qwen3_7_text_embedding"
        ]
        challengers = phase_three("qwen3_7_text_embedding")
        records = [
            Record(candidate, semantic_gain if candidate.chunker == "semantic_boundary" else fixed_weak)
            for candidate in challengers
        ]
        self.assertEqual(select_chunk_challenger(records, baseline), "semantic_boundary")

        no_gain = [Record(candidate, baseline_metrics) for candidate in challengers]
        self.assertIsNone(select_chunk_challenger(no_gain, baseline))


if __name__ == "__main__":
    unittest.main()
