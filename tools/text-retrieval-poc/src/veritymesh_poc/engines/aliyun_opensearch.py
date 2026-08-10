from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from ..domain import Chunk, ContractError, EmbeddingSpace, IndexedChunk, SearchHit, SearchScope


@dataclass(frozen=True)
class OpenSearchVectorConfig:
    endpoint: str
    instance_id: str
    access_user_name: str
    access_pass_word: str
    data_source_name: str
    table_name: str
    key_field: str = "chunk_id"
    vector_field: str = "vector"
    namespace: str = "default"
    timeout_seconds: float = 30.0
    rrf_rank_constant: int = 60


class AliyunOpenSearchVectorEngine:
    """Adapter for Alibaba Cloud OpenSearch Vector Search Edition's official SDK."""

    name = "aliyun_opensearch_vector"

    def __init__(self, config: OpenSearchVectorConfig, client: Any | None = None):
        self.config = config
        self._client = client or self._build_client(config)
        self._revoked_revisions: set[str] = set()
        self._idempotency: dict[str, str] = {}

    def active(self) -> Any:
        return self._client.active()

    def stage(self, items: list[IndexedChunk], idempotency_key: str) -> None:
        if not items:
            raise ContractError("cannot stage an empty chunk set")
        self._remember_idempotency(
            "stage",
            idempotency_key,
            "\n".join(sorted(f"{item.chunk.chunk_id}:{item.embedding_space_fingerprint}" for item in items)),
        )
        models = _sdk_models()
        actions = [{"cmd": "add", "fields": _fields(item, self.config.vector_field)} for item in items]
        request = models.PushDocumentsRequest(
            headers={"X-VerityMesh-Idempotency-Key": idempotency_key},
            body=actions,
        )
        response = self._client.push_documents(self.config.data_source_name, self.config.key_field, request)
        _raise_if_sdk_error(response, "OpenSearch push_documents")

    def lexical_search(self, query: str, scope: SearchScope, top_k: int) -> list[SearchHit]:
        models = _sdk_models()
        request = models.SearchRequest(
            table_name=self.config.table_name,
            size=top_k,
            output_fields=_output_fields(),
            text=models.TextQuery(query_string=query, filter=self._filter_expression(scope)),
        )
        response = self._client.search(request)
        return _parse_hits(response, source="bm25")

    def vector_search(
        self,
        vector: tuple[float, ...],
        space: EmbeddingSpace,
        scope: SearchScope,
        top_k: int,
    ) -> list[SearchHit]:
        models = _sdk_models()
        request = models.SearchRequest(
            table_name=self.config.table_name,
            size=top_k,
            output_fields=_output_fields(),
            knn=models.QueryRequest(
                table_name=self.config.table_name,
                vector=list(vector),
                namespace=self.config.namespace,
                top_k=top_k,
                filter=self._filter_expression(scope, embedding_space_fingerprint=space.fingerprint),
                output_fields=_output_fields(),
            ),
        )
        response = self._client.search(request)
        hits = _parse_hits(response, source="vector", expected_space=space.fingerprint)
        for hit in hits:
            if hit.chunk and hit.chunk.knowledge_release_id != scope.knowledge_release_id:
                raise ContractError("OpenSearch returned a document outside the requested release")
        return hits

    def hybrid_search(self, query: str, vector: tuple[float, ...], scope: SearchScope, top_k: int) -> list[SearchHit]:
        """Exercise the product's native text + KNN + RRF request for capability preflight."""
        models = _sdk_models()
        request = models.SearchRequest(
            table_name=self.config.table_name,
            size=top_k,
            output_fields=_output_fields(),
            knn=models.QueryRequest(
                table_name=self.config.table_name,
                vector=list(vector),
                namespace=self.config.namespace,
                top_k=top_k,
                filter=self._filter_expression(scope),
            ),
            text=models.TextQuery(query_string=query, filter=self._filter_expression(scope)),
            rank=models.RankQuery(rrf={"rankConstant": str(self.config.rrf_rank_constant)}),
        )
        response = self._client.search(request)
        return _parse_hits(response, source="hybrid")

    def _filter_expression(self, scope: SearchScope, *, embedding_space_fingerprint: str | None = None) -> str:
        expression = _filter_expression(scope)
        if embedding_space_fingerprint:
            expression += f" AND embedding_space_fingerprint = {_quote_value(embedding_space_fingerprint)}"
        if self._revoked_revisions:
            denied = " OR ".join(
                f"knowledge_revision_id = {_quote_value(revision)}"
                for revision in sorted(self._revoked_revisions)
            )
            expression += f" AND NOT ({denied})"
        return expression

    def delete_document(self, document_id: str, *, configuration_id: str, release_id: str, idempotency_key: str, chunk_ids: list[str] | None = None) -> None:
        if not chunk_ids:
            raise ContractError(
                "OpenSearch deletion needs the deterministic chunk IDs; a document ID is not the configured primary key"
            )
        self._remember_idempotency("delete_document", idempotency_key, "\x1f".join(sorted(chunk_ids)))
        models = _sdk_models()
        request = models.PushDocumentsRequest(
            headers={"X-VerityMesh-Idempotency-Key": idempotency_key},
            body=[{"cmd": "delete", "fields": {self.config.key_field: chunk_id}} for chunk_id in chunk_ids],
        )
        response = self._client.push_documents(self.config.data_source_name, self.config.key_field, request)
        _raise_if_sdk_error(response, "OpenSearch delete")

    def revoke_revision(self, revision_id: str, *, configuration_id: str, release_id: str, idempotency_key: str) -> None:
        self._remember_idempotency("revoke_revision", idempotency_key, revision_id)
        self._revoked_revisions.add(revision_id)

    def _remember_idempotency(self, operation: str, key: str, payload: str) -> None:
        from hashlib import sha256

        signature = sha256(f"{operation}\x1f{payload}".encode("utf-8")).hexdigest()
        prior = self._idempotency.get(key)
        if prior is not None and prior != signature:
            raise ContractError(f"idempotency key reused with a different {operation} payload")
        self._idempotency[key] = signature

    @staticmethod
    def _build_client(config: OpenSearchVectorConfig) -> Any:
        try:
            from alibabacloud_ha3engine_vector import client as sdk_client
            from alibabacloud_ha3engine_vector import models
        except ImportError as error:
            raise RuntimeError(
                "install alibabacloud-ha3engine-vector or provide an injected client"
            ) from error
        sdk_config = models.Config(
            endpoint=config.endpoint,
            instance_id=config.instance_id,
            protocol="https",
            access_user_name=config.access_user_name,
            access_pass_word=config.access_pass_word,
        )
        return sdk_client.Client(sdk_config)


def _sdk_models() -> Any:
    try:
        from alibabacloud_ha3engine_vector import models
    except ImportError as error:
        raise RuntimeError("install alibabacloud-ha3engine-vector to use OpenSearch adapter") from error
    return models


def _fields(item: IndexedChunk, vector_field: str = "vector") -> dict[str, Any]:
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
        "effective_from": chunk.effective_from or "",
        "effective_to": chunk.effective_to or "",
        "revoked": False,
        "embedding_space_fingerprint": item.embedding_space_fingerprint,
        "configuration_id": item.configuration_id,
        vector_field: list(item.vector),
    }


def _output_fields() -> list[str]:
    return [
        "chunk_id", "chunker_version", "document_id", "knowledge_revision_id", "project_id", "project_version",
        "locale", "access_segment", "knowledge_release_id", "knowledge_space_id", "citation_url",
        "title", "section", "text", "start_char", "end_char", "effective_from", "effective_to",
        "embedding_space_fingerprint", "configuration_id",
    ]


def _filter_expression(scope: SearchScope) -> str:
    parts = [
        f"project_id = {_quote_value(scope.project_id)}",
        f"project_version = {_quote_value(scope.project_version)}",
        f"locale = {_quote_value(scope.locale)}",
        f"knowledge_release_id = {_quote_value(scope.knowledge_release_id)}",
        f"configuration_id = {_quote_value(scope.configuration_id)}",
        "revoked = false",
    ]
    access = " OR ".join(f"access_segment = {_quote_value(value)}" for value in scope.allowed_access_segments)
    parts.append(f"({access})")
    if scope.now:
        parts.append(f"(effective_from = '' OR effective_from <= {_quote_value(scope.now)})")
        parts.append(f"(effective_to = '' OR effective_to >= {_quote_value(scope.now)})")
    return " AND ".join(parts)


def _quote_value(value: str) -> str:
    return "'" + value.replace("'", "\\'") + "'"


def _parse_hits(response: Any, *, source: str, expected_space: str | None = None) -> list[SearchHit]:
    body = getattr(response, "body", response)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenSearch response body is not JSON") from error
    if not isinstance(body, dict):
        raise RuntimeError("OpenSearch response body is not an object")
    raw_hits = body.get("hits") or body.get("result", {}).get("hits") or body.get("data") or []
    if isinstance(raw_hits, dict):
        raw_hits = raw_hits.get("hit") or raw_hits.get("items") or []
    hits: list[SearchHit] = []
    for index, raw in enumerate(raw_hits, start=1):
        if not isinstance(raw, dict):
            continue
        fields = raw.get("fields") or raw.get("_source") or raw.get("doc") or raw
        if not isinstance(fields, dict):
            continue
        if expected_space and _first(fields, "embedding_space_fingerprint", default=None) != expected_space:
            raise ContractError("OpenSearch returned a mixed embedding space")
        try:
            chunk = Chunk(
                chunk_id=str(_first(fields, "chunk_id")),
                chunker_version=str(_first(fields, "chunker_version", default="cloud-projection")),
                document_id=str(_first(fields, "document_id")),
                knowledge_revision_id=str(_first(fields, "knowledge_revision_id")),
                project_id=str(_first(fields, "project_id")),
                project_version=str(_first(fields, "project_version")),
                locale=str(_first(fields, "locale")),
                access_segment=str(_first(fields, "access_segment")),
                knowledge_release_id=str(_first(fields, "knowledge_release_id")),
                knowledge_space_id=str(_first(fields, "knowledge_space_id")),
                citation_url=str(_first(fields, "citation_url")),
                title=str(_first(fields, "title", default="")),
                section=str(_first(fields, "section", default="")),
                text=str(_first(fields, "text")),
                start_char=int(_first(fields, "start_char", default=0)),
                end_char=int(_first(fields, "end_char", default=0)),
                effective_from=_first(fields, "effective_from", default=None),
                effective_to=_first(fields, "effective_to", default=None),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("OpenSearch hit does not satisfy the PoC serving schema") from error
        score = float(raw.get("score", raw.get("_score", 0.0)))
        hits.append(SearchHit(chunk, score, index, source, lexical_score=score if source == "bm25" else None, vector_score=score if source == "vector" else None))
    return hits


def _first(fields: dict[str, Any], key: str, default: Any = ...):
    if key not in fields:
        if default is ...:
            raise KeyError(key)
        return default
    value = fields[key]
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def _raise_if_sdk_error(response: Any, operation: str) -> None:
    body = getattr(response, "body", response)
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
    else:
        parsed = body
    if isinstance(parsed, dict) and (
        parsed.get("error")
        or parsed.get("errors")
        or (parsed.get("code") not in (None, "", 0, "200", 200))
    ):
        raise RuntimeError(f"{operation} returned an error response")
