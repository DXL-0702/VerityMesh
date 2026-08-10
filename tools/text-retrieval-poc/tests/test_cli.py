from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from veritymesh_poc.cli import _validate_elasticsearch_contract, main


class CliTests(unittest.TestCase):
    def test_standard_analyzer_is_allowed_only_as_explicit_benchmark(self) -> None:
        _validate_elasticsearch_contract(
            {
                "index_analyzer": "standard",
                "search_analyzer": "standard",
                "analysis_profile_version": "bm25-multifield-standard-benchmark-v1",
                "dictionary_fingerprint": "none",
                "synonym_fingerprint": "none",
            }
        )
        with self.assertRaises(ValueError):
            _validate_elasticsearch_contract(
                {
                    "index_analyzer": "standard",
                    "search_analyzer": "standard",
                    "analysis_profile_version": "bm25-multifield-ik-v1",
                }
            )

    def test_plan_renders_staged_matrix_without_cartesian_expansion(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = main(
                [
                    "plan",
                    "--winning-embedding",
                    "qwen3_7_text_embedding",
                    "--winning-chunker",
                    "semantic_boundary",
                    "--winning-reranker",
                    "qwen3_rerank",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(len(json.loads(output.getvalue())), 14)

    def test_local_validate_generates_human_and_machine_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            result = main(["local-validate", "--output", str(output)])
            self.assertEqual(result, 0)
            self.assertTrue(output.with_suffix(".md").is_file())
            self.assertTrue(output.with_suffix(".json").is_file())
            payload = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            decision_ids = {
                decision_id
                for item in payload["provisional_decision"]["recommended_stack"]
                for decision_id in item["decision_ids"]
            }
            self.assertIn("RET-010", decision_ids)
            self.assertIn("MODEL-027", decision_ids)


if __name__ == "__main__":
    unittest.main()
