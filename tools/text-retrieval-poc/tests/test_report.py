from __future__ import annotations

from dataclasses import dataclass
import unittest

from veritymesh_poc.domain import EvidenceLevel
from veritymesh_poc.matrix import MatrixCandidate, phase_four, phase_one, phase_three, phase_two
from veritymesh_poc.metrics import RetrievalMetrics
from veritymesh_poc.report import _decision


@dataclass(frozen=True)
class ReportRecord:
    candidate: MatrixCandidate
    metrics: RetrievalMetrics | None
    evidence_level: EvidenceLevel = EvidenceLevel.CLOUD_PRODUCT
    hard_gates_passed: bool = True
    error: str | None = None


def metrics(
    *,
    recall: float = 0.95,
    ndcg: float = 0.86,
    mrr: float = 0.85,
    top3: float = 0.90,
    p95_ms: float = 300.0,
) -> RetrievalMetrics:
    return RetrievalMetrics(10, recall, ndcg, mrr, top3, p95_ms, p95_ms, p95_ms)


def complete_records(
    *,
    embedding_outcome: str = "qwen",
    reranker_outcome: str = "qwen",
    chunk_outcome: str = "structure_aware",
    include_phase_four: bool = False,
    hard_gates_passed: bool = True,
) -> list[ReportRecord]:
    baseline = metrics()
    weaker_embedding = metrics(recall=0.93, ndcg=0.84, mrr=0.83, top3=0.88)
    qwen_reranker = metrics(ndcg=0.89, mrr=0.88, top3=0.92)
    gte_reranker = metrics(ndcg=0.87, mrr=0.86, top3=0.91)
    if reranker_outcome == "none":
        qwen_reranker = baseline
        gte_reranker = baseline
    elif reranker_outcome == "gte":
        qwen_reranker = metrics(ndcg=0.88, mrr=0.87, top3=0.91)
        gte_reranker = metrics(ndcg=0.91, mrr=0.90, top3=0.93)

    records: list[ReportRecord] = []
    for candidate in phase_one():
        candidate_metrics = baseline if candidate.embedding == "qwen3_7_text_embedding" else weaker_embedding
        if embedding_outcome == "v4":
            candidate_metrics = weaker_embedding if candidate.embedding == "qwen3_7_text_embedding" else baseline
        records.append(ReportRecord(candidate, candidate_metrics, hard_gates_passed=hard_gates_passed))
    for candidate in phase_two("qwen3_7_text_embedding"):
        candidate_metrics = qwen_reranker if candidate.reranker == "qwen3_rerank" else gte_reranker
        records.append(ReportRecord(candidate, candidate_metrics, hard_gates_passed=hard_gates_passed))
    for candidate in phase_three("qwen3_7_text_embedding"):
        candidate_metrics = baseline
        if chunk_outcome == "semantic_boundary" and candidate.chunker == "semantic_boundary":
            candidate_metrics = metrics(ndcg=0.89, mrr=0.88, top3=0.92)
        records.append(ReportRecord(candidate, candidate_metrics, hard_gates_passed=hard_gates_passed))
    if include_phase_four:
        for candidate in phase_four("qwen3_7_text_embedding", "semantic_boundary", "qwen3_rerank"):
            records.append(
                ReportRecord(
                    candidate,
                    metrics(ndcg=0.91, mrr=0.90, top3=0.93),
                    hard_gates_passed=hard_gates_passed,
                )
            )
    return records


class ReportDecisionTests(unittest.TestCase):
    def test_primary_stack_is_selected_only_after_relative_gates_pass(self) -> None:
        decision = _decision(complete_records())
        self.assertEqual(decision["overall_status"], "SELECTED")

    def test_reranker_without_material_gain_cannot_create_a_false_winner(self) -> None:
        decision = _decision(complete_records(reranker_outcome="none"))
        self.assertEqual(decision["overall_status"], "CONFIRMED_WITH_GATES")

    def test_reranker_challenger_win_does_not_select_the_provisional_primary(self) -> None:
        decision = _decision(complete_records(reranker_outcome="gte"))
        self.assertEqual(decision["overall_status"], "CONFIRMED_WITH_GATES")

    def test_embedding_challenger_win_does_not_select_the_provisional_primary(self) -> None:
        decision = _decision(complete_records(embedding_outcome="v4"))
        self.assertEqual(decision["overall_status"], "CONFIRMED_WITH_GATES")

    def test_chunk_challenger_requires_phase_four_confirmation(self) -> None:
        incomplete = _decision(complete_records(chunk_outcome="semantic_boundary"))
        self.assertEqual(incomplete["overall_status"], "CONFIRMED_WITH_GATES")

        confirmed = _decision(
            complete_records(
                chunk_outcome="semantic_boundary",
                include_phase_four=True,
            )
        )
        self.assertEqual(confirmed["overall_status"], "SELECTED")

    def test_unclosed_cloud_hard_gates_cannot_select_the_stack(self) -> None:
        decision = _decision(complete_records(hard_gates_passed=False))
        self.assertEqual(decision["overall_status"], "CONFIRMED_WITH_GATES")


if __name__ == "__main__":
    unittest.main()
