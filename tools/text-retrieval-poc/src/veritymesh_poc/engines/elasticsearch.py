from __future__ import annotations

from dataclasses import dataclass
import base64
from hashlib import sha256
import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..domain import ContractError, EmbeddingSpace, IndexedChunk, SearchHit, SearchScope, Chunk


@dataclass(frozen=True)
class ElasticsearchConfig:
    endpoint: str
    index_prefix: str = "veritymesh-poc"
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 30.0
    verify_tls: bool = True
    refresh: str = "wait_for"
    index_analyzer: str = "ik_max_word"
    search_analyzer: str = "ik_smart"
    analysis_profile_version: str = "bm25-multifield-ik-v1"
    dictionary_fingerprint: str = "none"
    synonym_fingerprint: str = "none"


class ElasticsearchRestEngine:
    """Minimal REST adapter for Alibaba Cloud Elasticsearch 8.17-compatible clusters."""

    name = "aliyun_elasticsearch"

    def __init__(self, config: ElasticsearchConfig):
        endpoint = config.endpoint.rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise ContractError("Elasticsearch endpoint must include http:// or https://")
        self.config = config
        self.endpoint = endpoint
        self._idempotency: dict[str, str] = {}

    def stage(self, items: list[IndexedChunk], idempotency_key: str) -> None:
        if not items:
            raise ContractError("cannot stage an empty chunk set")
        dimensions = {len(item.vector) for item in items}
        if len(dimensions) != 1:
            raise ContractError("one Elasticsearch index cannot contain mixed vector dimensions")
        index_names = {self.index_name(item.configuration_id, item.chunk.knowledge_release_id) for item in items}
        if len(index_names) != 1:
            raise ContractError("stage batch must belong to one configuration and release")
        self._remember_idempotency(
            "stage",
            idempotency_key,
            "\n".join(sorted(f"{item.chunk.chunk_id}:{item.embedding_space_fingerprint}" for item in items)),
        )
        index_name = next(iter(index_names))
        self._ensure_index(index_name, next(iter(dimensions)))
        lines: list[str] = []
        for item in items:
            lines.append(json.dumps({"index": {"_index": index_name, "_id": item.chunk.chunk_id}}))
            lines.append(json.dumps(_source(item), ensure_ascii=False))
        response = self._request(
            "POST",
            f"/{quote(index_name)}/_bulk?refresh={quote(self.config.refresh)}",
            "\n".join(lines) + "\n",
            content_type="application/x-ndjson",
        )
        if response.get("errors"):
            raise RuntimeError("Elasticsearch bulk stage returned item errors")

    def lexical_search(self, query: str, scope: SearchScope, top_k: int) -> list[SearchHit]:
        body = {
            "size": top_k,
            "track_total_hits": False,
            "query": {
                "bool": {
                    "filter": _filters(scope),
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "type": "best_fields",
                                "tie_breaker": 0.2,
                                "fields": [
                                    "title^4",
                                    "section^3",
                                    "search_text^2",
                                    "title.standard^2",
                                    "section.standard^1.5",
                                    "search_text.standard",
                                    "title.identifier^2",
                                    "section.identifier^2",
                                    "search_text.identifier^1.5",
                                ],
                            }
                        }
                    ],
                }
            },
        }
        return self._search(scope, body, source="bm25", score_field="_score")

    def vector_search(
        self,
        vector: tuple[float, ...],
        space: EmbeddingSpace,
        scope: SearchScope,
        top_k: int,
    ) -> list[SearchHit]:
        body = {
            "size": top_k,
            "track_total_hits": False,
            "knn": {
                "field": "vector",
                "query_vector": list(vector),
                "k": top_k,
                "num_candidates": max(100, top_k * 10),
                "filter": _filters(scope),
            },
        }
        return self._search(scope, body, source="vector", score_field="_score", expected_space=space.fingerprint)

    def revoke_revision(self, revision_id: str, *, configuration_id: str, release_id: str, idempotency_key: str) -> None:
        self._remember_idempotency("revoke_revision", idempotency_key, revision_id)
        index_name = self.index_name(configuration_id, release_id)
        body = {
            "script": {"source": "ctx._source.revoked = true", "lang": "painless"},
            "query": {"term": {"knowledge_revision_id": revision_id}},
        }
        self._request("POST", f"/{quote(index_name)}/_update_by_query?refresh={quote(self.config.refresh)}", body)

    def delete_document(self, document_id: str, *, configuration_id: str, release_id: str, idempotency_key: str) -> None:
        self._remember_idempotency("delete_document", idempotency_key, document_id)
        index_name = self.index_name(configuration_id, release_id)
        body = {"query": {"term": {"document_id": document_id}}}
        self._request("POST", f"/{quote(index_name)}/_delete_by_query?refresh={quote(self.config.refresh)}", body)

    def index_name(self, configuration_id: str, release_id: str) -> str:
        analysis_fingerprint = sha256(
            "\x1f".join(
                (
                    self.config.analysis_profile_version,
                    self.config.index_analyzer,
                    self.config.search_analyzer,
                    self.config.dictionary_fingerprint,
                    self.config.synonym_fingerprint,
                )
            ).encode("utf-8")
        ).hexdigest()[:12]
        return (
            f"{_safe(self.config.index_prefix)}-{_safe(configuration_id)}-"
            f"{analysis_fingerprint}-{_safe(release_id)}"
        )

    def activate_alias(self, alias: str, *, configuration_id: str, release_id: str, idempotency_key: str) -> None:
        """Atomically point a binding alias to a validated release projection."""
        self._remember_idempotency("activate_alias", idempotency_key, f"{alias}\x1f{configuration_id}\x1f{release_id}")
        wildcard = f"{_safe(self.config.index_prefix)}-{_safe(configuration_id)}-*"
        body = {
            "actions": [
                {"remove": {"index": wildcard, "alias": alias, "must_exist": False}},
                {"add": {"index": self.index_name(configuration_id, release_id), "alias": alias}},
            ]
        }
        self._request("POST", "/_aliases", body)

    def delete_poc_index(self, configuration_id: str, release_id: str) -> None:
        """Delete only a caller-created PoC release index after a mutation suite."""
        if not configuration_id.startswith("contract-"):
            raise ContractError("refusing to delete an index outside the cloud-contract naming scope")
        self._request("DELETE", f"/{quote(self.index_name(configuration_id, release_id))}")

    def _ensure_index(self, index_name: str, dimension: int) -> None:
        analyzed_text = _analyzed_text_mapping(
            self.config.index_analyzer,
            self.config.search_analyzer,
        )
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "identifier_v1": {
                            "type": "custom",
                            "tokenizer": "whitespace",
                            "filter": ["lowercase"],
                        }
                    }
                },
            },
            "mappings": {
                "_meta": {
                    "analysis_profile_version": self.config.analysis_profile_version,
                    "dictionary_fingerprint": self.config.dictionary_fingerprint,
                    "synonym_fingerprint": self.config.synonym_fingerprint,
                },
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "chunker_version": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "knowledge_revision_id": {"type": "keyword"},
                    "project_id": {"type": "keyword"},
                    "project_version": {"type": "keyword"},
                    "locale": {"type": "keyword"},
                    "access_segment": {"type": "keyword"},
                    "knowledge_release_id": {"type": "keyword"},
                    "knowledge_space_id": {"type": "keyword"},
                    "citation_url": {"type": "keyword", "index": False},
                    "title": analyzed_text,
                    "section": analyzed_text,
                    "text": {"type": "text"},
                    "search_text": analyzed_text,
                    "start_char": {"type": "integer"},
                    "end_char": {"type": "integer"},
                    "effective_from": {"type": "keyword"},
                    "effective_to": {"type": "keyword"},
                    "revoked": {"type": "boolean"},
                    "embedding_space_fingerprint": {"type": "keyword"},
                    "configuration_id": {"type": "keyword"},
                    "vector": {"type": "dense_vector", "dims": dimension, "index": True, "similarity": "cosine"},
                }
            },
        }
        try:
            self._request("PUT", f"/{quote(index_name)}", mapping)
        except RuntimeError as error:
            if "resource_already_exists_exception" not in str(error):
                raise

    def _search(
        self,
        scope: SearchScope,
        body: dict[str, Any],
        *,
        source: str,
        score_field: str,
        expected_space: str | None = None,
    ) -> list[SearchHit]:
        index_name = self.index_name(scope.configuration_id, scope.knowledge_release_id)
        response = self._request("POST", f"/{quote(index_name)}/_search", body)
        raw_hits = response.get("hits", {}).get("hits", [])
        results: list[SearchHit] = []
        for index, raw in enumerate(raw_hits, start=1):
            source_doc = raw.get("_source") or {}
            if expected_space and source_doc.get("embedding_space_fingerprint") != expected_space:
                raise ContractError("Elasticsearch returned a mixed embedding space")
            chunk = _chunk_from_source(source_doc)
            score = float(raw.get(score_field, 0.0))
            results.append(
                SearchHit(
                    chunk=chunk,
                    score=score,
                    rank=index,
                    source=source,
                    lexical_score=score if source == "bm25" else None,
                    vector_score=score if source == "vector" else None,
                )
            )
        return results

    def _request(self, method: str, path: str, body: Any = None, *, content_type: str = "application/json") -> dict[str, Any]:
        headers = {"Content-Type": content_type, "User-Agent": "veritymesh-text-retrieval-poc/0.1"}
        if self.config.api_key:
            headers["Authorization"] = f"ApiKey {self.config.api_key}"
        elif self.config.username is not None and self.config.password is not None:
            token = base64.b64encode(f"{self.config.username}:{self.config.password}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else (body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8"))
        request = Request(self.endpoint + path, data=data, headers=headers, method=method)
        context = None
        if self.endpoint.startswith("https://"):
            context = ssl.create_default_context() if self.config.verify_tls else ssl._create_unverified_context()
        try:
            with urlopen(request, timeout=self.config.timeout_seconds, context=context) as response:
                raw = response.read()
        except HTTPError as error:
            detail = error.read(512).decode("utf-8", errors="replace")
            raise RuntimeError(f"Elasticsearch HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Elasticsearch request failed: {error.reason}") from error
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Elasticsearch returned invalid JSON") from error
        if not isinstance(parsed, dict):
            raise RuntimeError("Elasticsearch returned a non-object JSON body")
        return parsed

    def _remember_idempotency(self, operation: str, key: str, payload: str) -> None:
        signature = sha256(f"{operation}\x1f{payload}".encode("utf-8")).hexdigest()
        prior = self._idempotency.get(key)
        if prior is not None and prior != signature:
            raise ContractError(f"idempotency key reused with a different {operation} payload")
        self._idempotency[key] = signature


def _filters(scope: SearchScope) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = [
        {"term": {"project_id": scope.project_id}},
        {"term": {"project_version": scope.project_version}},
        {"term": {"locale": scope.locale}},
        {"term": {"knowledge_release_id": scope.knowledge_release_id}},
        {"term": {"configuration_id": scope.configuration_id}},
        {"term": {"revoked": False}},
        {"terms": {"access_segment": list(scope.allowed_access_segments)}},
    ]
    if scope.now:
        filters.extend(
            [
                {"bool": {"should": [{"bool": {"must_not": {"exists": {"field": "effective_from"}}}}, {"range": {"effective_from": {"lte": scope.now}}}], "minimum_should_match": 1}},
                {"bool": {"should": [{"bool": {"must_not": {"exists": {"field": "effective_to"}}}}, {"range": {"effective_to": {"gte": scope.now}}}], "minimum_should_match": 1}},
            ]
        )
    return filters


def _source(item: IndexedChunk) -> dict[str, Any]:
    chunk = item.chunk
    return {
        "chunk_id": chunk.chunk_id,
        "chunker_version": chunk.chunker_version,
        "document_id": chunk.document_id,
        "knowledge_revision_id": chunk.knowledge_revision_id,
        "project_id": chunk.project_id,
        "project_version": chunk.project_version,
        "locale": chunk.locale,
        "access_segment": chunk.access_segment,
        "knowledge_release_id": chunk.knowledge_release_id,
        "knowledge_space_id": chunk.knowledge_space_id,
        "citation_url": chunk.citation_url,
        "title": chunk.title,
        "section": chunk.section,
        "text": chunk.text,
        "search_text": chunk.search_text,
        "start_char": chunk.start_char,
        "end_char": chunk.end_char,
        "effective_from": chunk.effective_from,
        "effective_to": chunk.effective_to,
        "revoked": False,
        "embedding_space_fingerprint": item.embedding_space_fingerprint,
        "configuration_id": item.configuration_id,
        "vector": list(item.vector),
    }


def _chunk_from_source(source: dict[str, Any]) -> Chunk:
    return Chunk(
        chunk_id=str(source["chunk_id"]),
        chunker_version=str(source.get("chunker_version", "cloud-projection")),
        document_id=str(source["document_id"]),
        knowledge_revision_id=str(source["knowledge_revision_id"]),
        project_id=str(source["project_id"]),
        project_version=str(source["project_version"]),
        locale=str(source["locale"]),
        access_segment=str(source["access_segment"]),
        knowledge_release_id=str(source["knowledge_release_id"]),
        knowledge_space_id=str(source["knowledge_space_id"]),
        citation_url=str(source["citation_url"]),
        title=str(source.get("title", "")),
        section=str(source.get("section", "")),
        text=str(source["text"]),
        start_char=int(source["start_char"]),
        end_char=int(source["end_char"]),
        effective_from=source.get("effective_from"),
        effective_to=source.get("effective_to"),
    )


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value).strip("-")[:80] or "poc"


def _analyzed_text_mapping(index_analyzer: str, search_analyzer: str) -> dict[str, Any]:
    return {
        "type": "text",
        "analyzer": index_analyzer,
        "search_analyzer": search_analyzer,
        "fields": {
            "standard": {"type": "text", "analyzer": "standard"},
            "identifier": {"type": "text", "analyzer": "identifier_v1"},
            "keyword": {"type": "keyword", "ignore_above": 1024},
        },
    }
