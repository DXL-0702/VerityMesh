from __future__ import annotations

import unittest

from veritymesh_poc.cloud_gates import run_cloud_contract_gates
from veritymesh_poc.domain import EmbeddingSpace, IndexedChunk, QueryCase, SearchHit, SearchScope
from veritymesh_poc.embeddings import DeterministicHashEmbedding, ProviderError
from veritymesh_poc.engines.elasticsearch import ElasticsearchRestEngine
from veritymesh_poc.gates import HARD_GATES, all_gates_pass, run_in_memory_contract_gates
from veritymesh_poc.retrieval import HybridRetriever, InMemoryServingEngine
from veritymesh_poc.tokenization import HuggingFaceOffsetTokenizer

from support import document


class ContractGateTests(unittest.TestCase):
    def test_all_hard_contract_gates_pass(self) -> None:
        results = run_in_memory_contract_gates()
        self.assertEqual([result.gate for result in results], list(HARD_GATES))
        self.assertTrue(all_gates_pass(results), results)

    def test_mutating_cloud_gate_orchestration_runs_end_to_end(self) -> None:
        class FakeElasticsearch(ElasticsearchRestEngine):
            def __init__(self):
                self.memory = InMemoryServingEngine()

            def stage(self, items: list[IndexedChunk], idempotency_key: str) -> None:
                self.memory.stage(items, idempotency_key)

            def lexical_search(self, query: str, scope: SearchScope, top_k: int) -> list[SearchHit]:
                return self.memory.lexical_search(query, scope, top_k)

            def vector_search(
                self,
                vector: tuple[float, ...],
                space: EmbeddingSpace,
                scope: SearchScope,
                top_k: int,
            ) -> list[SearchHit]:
                return self.memory.vector_search(vector, space, scope, top_k)

            def revoke_revision(self, revision_id: str, **kwargs) -> None:
                self.memory.revoke_revision(revision_id, kwargs["idempotency_key"])

            def delete_document(self, document_id: str, **kwargs) -> None:
                self.memory.delete_document(document_id, kwargs["idempotency_key"])

            def activate_alias(self, alias: str, **kwargs) -> None:
                return None

            def delete_poc_index(self, configuration_id: str, release_id: str) -> None:
                return None

        results = run_cloud_contract_gates(FakeElasticsearch(), DeterministicHashEmbedding())
        self.assertTrue(all(result.passed for result in results), results)

    def test_production_tokenizer_rejects_remote_loading_and_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned local artifact"):
            HuggingFaceOffsetTokenizer("unused", revision="fixed", local_files_only=False)
        with self.assertRaisesRegex(ValueError, "must not execute remote code"):
            HuggingFaceOffsetTokenizer("unused", revision="fixed", trust_remote_code=True)

    def test_runtime_vector_failure_degrades_to_bm25(self) -> None:
        source = document(text="审计日志保留 180 天。")
        working = DeterministicHashEmbedding()
        engine = InMemoryServingEngine()
        from veritymesh_poc.chunking import StructureAwareChunker

        chunk = StructureAwareChunker().chunk(source)[0]
        batch = working.embed_documents([chunk.search_text])
        engine.stage(
            [IndexedChunk(chunk, batch.vectors[0], batch.space.fingerprint, "contract")],
            "stage",
        )

        class FailingEmbedding(DeterministicHashEmbedding):
            def embed_queries(self, texts):
                raise ProviderError("provider unavailable")

        hits = HybridRetriever(engine, FailingEmbedding()).search(
            QueryCase(
                query_id="q-runtime-fallback",
                text="审计日志",
                project_id=source.project_id,
                project_version=source.project_version,
                locale=source.locale,
                allowed_access_segments=(source.access_segment,),
                knowledge_release_id=source.knowledge_release_id,
                relevant_documents={source.document_id: 1},
            ),
            configuration_id="contract",
        )
        self.assertEqual(hits[0].chunk.document_id, source.document_id)

        with self.assertRaises(ProviderError):
            HybridRetriever(engine, FailingEmbedding(), allow_vector_fallback=False).search(
                QueryCase(
                    query_id="q-strict",
                    text="审计日志",
                    project_id=source.project_id,
                    project_version=source.project_version,
                    locale=source.locale,
                    allowed_access_segments=(source.access_segment,),
                    knowledge_release_id=source.knowledge_release_id,
                    relevant_documents={source.document_id: 1},
                ),
                configuration_id="contract",
            )


if __name__ == "__main__":
    unittest.main()
