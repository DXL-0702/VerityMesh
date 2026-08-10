from __future__ import annotations

import json
import math
import os
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from veritymesh_poc.embeddings import DashScopeEmbeddingAdapter, DashScopeEmbeddingConfig, ProviderError
from veritymesh_poc.engines import aliyun_opensearch
from veritymesh_poc.engines.elasticsearch import ElasticsearchConfig, ElasticsearchRestEngine
from veritymesh_poc.rerankers import (
    DashScopeReranker,
    DashScopeRerankerConfig,
    FallbackReranker,
    Reranker,
    RerankerProviderError,
)
from veritymesh_poc.domain import SearchHit
from veritymesh_poc.tokenization import UnicodeRegexTokenizer

from support import document, indexed_item, scope


class _Response:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AdapterTests(unittest.TestCase):
    def test_dashscope_native_embedding_request_has_role_and_dimension(self) -> None:
        captured = {}

        def fake_open(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({"output": {"embeddings": [{"text_index": 0, "embedding": [0.1, 0.2]}]}})

        config = DashScopeEmbeddingConfig(model="test-model", dimension=2)
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "not-a-real-secret"}), patch(
            "veritymesh_poc.embeddings.urlopen", fake_open
        ):
            adapter = DashScopeEmbeddingAdapter(config, tokenizer=UnicodeRegexTokenizer())
            batch = adapter.embed_queries(["查询"])
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in batch.vectors[0])), 1.0, places=6)
        self.assertEqual(captured["payload"]["parameters"], {"dimension": 2, "text_type": "query"})

    def test_dashscope_embedding_rejects_zero_vector(self) -> None:
        def fake_open(request, timeout):
            return _Response({"output": {"embeddings": [{"text_index": 0, "embedding": [0.0, 0.0]}]}})

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "not-a-real-secret"}), patch(
            "veritymesh_poc.embeddings.urlopen", fake_open
        ):
            adapter = DashScopeEmbeddingAdapter(
                DashScopeEmbeddingConfig(model="test-model", dimension=2),
                tokenizer=UnicodeRegexTokenizer(),
            )
            with self.assertRaises(ProviderError):
                adapter.embed_queries(["查询"])

    def test_dashscope_embedding_rejects_oversized_input_before_provider_call(self) -> None:
        adapter = DashScopeEmbeddingAdapter(
            DashScopeEmbeddingConfig(model="test-model", dimension=2, query_max_tokens=1),
            tokenizer=UnicodeRegexTokenizer(),
        )
        with self.assertRaisesRegex(ValueError, "silent truncation is forbidden"):
            adapter.embed_queries(["两个词"])

    def test_dashscope_reranker_preserves_provider_rank_order(self) -> None:
        first, _ = indexed_item()
        second, _ = indexed_item(
            document(document_id="doc-2", knowledge_revision_id="revision-2", text="API 限流为每分钟 120 次。")
        )
        hits = [SearchHit(first.chunk, 0.4, 1, "rrf"), SearchHit(second.chunk, 0.3, 2, "rrf")]
        captured = {}

        def fake_open(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({"output": {"results": [{"index": 1, "relevance_score": 0.95}, {"index": 0, "relevance_score": 0.5}]}})

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "not-a-real-secret"}), patch(
            "veritymesh_poc.rerankers.urlopen", fake_open
        ):
            reranker = DashScopeReranker(
                DashScopeRerankerConfig(model="qwen3-rerank"),
                tokenizer=UnicodeRegexTokenizer(),
            )
            ranked = reranker.rerank("限流", hits, 2)
        self.assertEqual([hit.chunk.document_id for hit in ranked], ["doc-2", "doc-1"])
        self.assertEqual(captured["payload"]["parameters"]["top_n"], 2)

    def test_dashscope_reranker_adapter_accepts_gte_challenger(self) -> None:
        item, _ = indexed_item()
        hit = SearchHit(item.chunk, 0.4, 1, "rrf")
        captured = {}

        def fake_open(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({"output": {"results": [{"index": 0, "relevance_score": 0.8}]}})

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "not-a-real-secret"}), patch(
            "veritymesh_poc.rerankers.urlopen", fake_open
        ):
            reranker = DashScopeReranker(
                DashScopeRerankerConfig(model="gte-rerank-v2", revision="fixed-v1"),
                tokenizer=UnicodeRegexTokenizer(),
            )
            reranker.rerank("审计", [hit], 1)
        self.assertEqual(captured["payload"]["model"], "gte-rerank-v2")
        self.assertIn("gte-rerank-v2:fixed-v1", reranker.version)

    def test_runtime_reranker_falls_back_to_rrf_without_retrying(self) -> None:
        item, _ = indexed_item()
        hit = SearchHit(item.chunk, 0.4, 1, "rrf")

        class FailingReranker(Reranker):
            version = "failing-v1"

            def __init__(self):
                self.calls = 0

            def rerank(self, query, hits, top_n):
                self.calls += 1
                raise RerankerProviderError("timeout")

        primary = FailingReranker()
        ranked = FallbackReranker(primary).rerank("审计", [hit], 1)
        self.assertEqual(primary.calls, 1)
        self.assertEqual(ranked[0].chunk.chunk_id, hit.chunk.chunk_id)

    def test_elasticsearch_vector_request_contains_all_security_filters(self) -> None:
        item, embedder = indexed_item()

        class Engine(ElasticsearchRestEngine):
            def __init__(self):
                super().__init__(ElasticsearchConfig(endpoint="https://example.invalid"))
                self.requests = []

            def _request(self, method, path, body=None, **kwargs):
                self.requests.append((method, path, body))
                if method == "PUT":
                    return {"acknowledged": True}
                if "_bulk" in path:
                    return {"errors": False}
                if "_search" in path:
                    source = {
                        "chunk_id": item.chunk.chunk_id,
                        "document_id": item.chunk.document_id,
                        "knowledge_revision_id": item.chunk.knowledge_revision_id,
                        "project_id": item.chunk.project_id,
                        "project_version": item.chunk.project_version,
                        "locale": item.chunk.locale,
                        "access_segment": item.chunk.access_segment,
                        "knowledge_release_id": item.chunk.knowledge_release_id,
                        "knowledge_space_id": item.chunk.knowledge_space_id,
                        "citation_url": item.chunk.citation_url,
                        "title": item.chunk.title,
                        "section": item.chunk.section,
                        "text": item.chunk.text,
                        "start_char": item.chunk.start_char,
                        "end_char": item.chunk.end_char,
                        "embedding_space_fingerprint": embedder.space.fingerprint,
                    }
                    return {"hits": {"hits": [{"_score": 1.0, "_source": source}]}}
                return {}

        engine = Engine()
        engine.stage([item], "stage-1")
        index_body = next(body for method, _, body in engine.requests if method == "PUT")
        self.assertEqual(index_body["mappings"]["properties"]["search_text"]["analyzer"], "ik_max_word")
        self.assertEqual(index_body["mappings"]["properties"]["search_text"]["search_analyzer"], "ik_smart")
        self.assertIn("standard", index_body["mappings"]["properties"]["search_text"]["fields"])
        self.assertIn("identifier", index_body["mappings"]["properties"]["search_text"]["fields"])
        query = embedder.embed_queries(["审计日志"])
        hits = engine.vector_search(query.vectors[0], query.space, scope(), 10)
        self.assertEqual(len(hits), 1)
        vector_body = next(body for _, path, body in engine.requests if "_search" in path)
        serialized = json.dumps(vector_body, ensure_ascii=False)
        for required in ("project_id", "project_version", "locale", "knowledge_release_id", "access_segment", "configuration_id", "revoked"):
            self.assertIn(required, serialized)

        engine.lexical_search("审计日志", scope(), 10)
        lexical_body = next(
            body
            for _, path, body in engine.requests
            if "_search" in path and "multi_match" in json.dumps(body)
        )
        fields = lexical_body["query"]["bool"]["must"][0]["multi_match"]["fields"]
        self.assertIn("title^4", fields)
        self.assertIn("search_text.identifier^1.5", fields)

    def test_opensearch_stage_uses_configured_vector_field_and_filter(self) -> None:
        item, _ = indexed_item()

        class PushDocumentsRequest:
            def __init__(self, headers=None, body=None):
                self.headers = headers
                self.body = body

        class TextQuery:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class QueryRequest:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class SearchRequest:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class RankQuery:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        Models = SimpleNamespace(
            PushDocumentsRequest=PushDocumentsRequest,
            TextQuery=TextQuery,
            QueryRequest=QueryRequest,
            SearchRequest=SearchRequest,
            RankQuery=RankQuery,
        )

        class Client:
            def __init__(self):
                self.push = None
                self.search_request = None

            def push_documents(self, *args):
                self.push = args
                return type("Response", (), {"body": json.dumps({"code": "200"})})()

            def search(self, request):
                self.search_request = request
                return type("Response", (), {"body": json.dumps({"hits": []})})()

        client = Client()
        config = aliyun_opensearch.OpenSearchVectorConfig(
            endpoint="example.invalid",
            instance_id="instance",
            access_user_name="user",
            access_pass_word="password",
            data_source_name="source",
            table_name="table",
            vector_field="embedding_v1024",
        )
        with patch("veritymesh_poc.engines.aliyun_opensearch._sdk_models", return_value=Models):
            engine = aliyun_opensearch.AliyunOpenSearchVectorEngine(config, client=client)
            engine.stage([item], "stage")
            action = client.push[2].body[0]
            self.assertIn("embedding_v1024", action["fields"])
            engine.lexical_search("审计日志", scope(), 10)
        filter_text = client.search_request.kwargs["text"].kwargs["filter"]
        self.assertIn("project_id", filter_text)
        self.assertIn("knowledge_release_id", filter_text)
        self.assertIn("revoked = false", filter_text)


if __name__ == "__main__":
    unittest.main()
