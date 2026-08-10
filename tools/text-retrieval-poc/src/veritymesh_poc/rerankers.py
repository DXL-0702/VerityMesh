from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .domain import SearchHit, ContractError
from .tokenization import OffsetTokenizer, count_tokens


class RerankerProviderError(RuntimeError):
    """The external reranker failed or returned an invalid ranking contract."""


class Reranker:
    name = "none"
    version = "none-v1"

    def rerank(self, query: str, hits: list[SearchHit], top_n: int) -> list[SearchHit]:
        raise NotImplementedError


class RRFOnlyReranker(Reranker):
    name = "rrf_only"
    version = "rrf-only-v1"

    def rerank(self, query: str, hits: list[SearchHit], top_n: int) -> list[SearchHit]:
        return [replace(hit, rank=index + 1) for index, hit in enumerate(hits[:top_n])]


class FallbackReranker(Reranker):
    """Runtime wrapper that fails over without hiding PoC candidate failures."""

    name = "fallback_reranker"

    def __init__(self, primary: Reranker, fallback: Reranker | None = None):
        self.primary = primary
        self.fallback = fallback or RRFOnlyReranker()
        self.version = f"{primary.version}->fallback:{self.fallback.version}"

    def rerank(self, query: str, hits: list[SearchHit], top_n: int) -> list[SearchHit]:
        try:
            return self.primary.rerank(query, hits, top_n)
        except RerankerProviderError:
            return self.fallback.rerank(query, hits, top_n)


class LexicalOverlapReranker(Reranker):
    """Local contract-test stand-in; never reported as a cloud model result."""

    name = "local_lexical_rerank"
    version = "local-lexical-rerank-v1"
    _token_pattern = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]", re.UNICODE)

    def rerank(self, query: str, hits: list[SearchHit], top_n: int) -> list[SearchHit]:
        query_terms = set(self._token_pattern.findall(query.lower()))
        scored = []
        for hit in hits:
            terms = set(self._token_pattern.findall(hit.chunk.search_text.lower()))
            overlap = len(query_terms & terms) / max(1, len(query_terms))
            scored.append(replace(hit, rerank_score=overlap, score=overlap))
        scored.sort(key=lambda hit: (hit.rerank_score or 0.0, hit.score), reverse=True)
        return [replace(hit, rank=index + 1) for index, hit in enumerate(scored[:top_n])]


@dataclass(frozen=True)
class DashScopeRerankerConfig:
    model: str = "qwen3-rerank"
    revision: str = "configured"
    region: str = "cn-beijing"
    api_key_env: str = "DASHSCOPE_API_KEY"
    endpoint: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    api_mode: str = "native"
    timeout_seconds: float = 1.0
    query_max_tokens: int = 512
    document_max_tokens: int = 1024
    max_documents: int = 50


class DashScopeReranker(Reranker):
    name = "dashscope_reranker"
    version = "dashscope-reranker-configured"

    def __init__(self, config: DashScopeRerankerConfig, *, tokenizer: OffsetTokenizer):
        if config.api_mode not in {"native", "compatible"}:
            raise ContractError(f"unsupported DashScope reranker api_mode: {config.api_mode}")
        if config.query_max_tokens <= 0 or config.document_max_tokens <= 0 or config.max_documents <= 0:
            raise ContractError("reranker limits must be positive")
        self.config = config
        self.tokenizer = tokenizer
        self.name = _slug(config.model)
        self.version = f"aliyun-bailian:{config.region}:{config.api_mode}:{config.model}:{config.revision}"

    def rerank(self, query: str, hits: list[SearchHit], top_n: int) -> list[SearchHit]:
        if not hits:
            return []
        if top_n <= 0:
            raise ContractError("reranker top_n must be positive")
        if len(hits) > self.config.max_documents:
            raise ContractError(
                f"reranker received {len(hits)} documents, exceeding max_documents={self.config.max_documents}"
            )
        query_tokens = count_tokens(self.tokenizer, query)
        if query_tokens > self.config.query_max_tokens:
            raise ContractError(
                f"reranker query exceeds {self.config.query_max_tokens} tokens: {query_tokens}"
            )
        documents = [hit.chunk.search_text for hit in hits]
        for index, document in enumerate(documents):
            document_tokens = count_tokens(self.tokenizer, document)
            if document_tokens > self.config.document_max_tokens:
                raise ContractError(
                    f"reranker document {index} exceeds {self.config.document_max_tokens} tokens: {document_tokens}"
                )
        if self.config.api_mode == "compatible":
            payload = {
                "model": self.config.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False,
            }
        else:
            payload = {
                "model": self.config.model,
                "input": {"query": query, "documents": documents},
                "parameters": {"top_n": top_n, "return_documents": False},
            }
        body = _post_json(
            self.config.endpoint,
            payload,
            api_key=_required_api_key(self.config.api_key_env),
            timeout=self.config.timeout_seconds,
        )
        results = _parse_results(body)
        if not results:
            raise RerankerProviderError("reranker returned no result list")
        ranked: list[SearchHit] = []
        seen_indexes: set[int] = set()
        for item in results:
            index = int(item.get("index", -1))
            if not 0 <= index < len(hits):
                raise RerankerProviderError("reranker returned an out-of-range document index")
            if index in seen_indexes:
                raise RerankerProviderError("reranker returned a duplicate document index")
            seen_indexes.add(index)
            score = float(item.get("relevance_score", item.get("score", 0.0)))
            if not math.isfinite(score):
                raise RerankerProviderError("reranker returned a non-finite score")
            ranked.append(replace(hits[index], rerank_score=score, score=score))
        return [replace(hit, rank=index + 1) for index, hit in enumerate(ranked[:top_n])]


DashScopeQwen3Reranker = DashScopeReranker


def _parse_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    output = body.get("output") if isinstance(body, dict) else None
    if isinstance(output, dict) and isinstance(output.get("results"), list):
        return output["results"]
    if isinstance(body.get("results"), list):
        return body["results"]
    return []


def _required_api_key(environment_name: str) -> str:
    value = os.environ.get(environment_name)
    if not value:
        raise RuntimeError(f"missing required credential environment variable: {environment_name}")
    return value


def _post_json(endpoint: str, payload: dict[str, Any], *, api_key: str, timeout: float) -> dict[str, Any]:
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "veritymesh-text-retrieval-poc/0.1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as error:
        raise RerankerProviderError(f"reranker provider returned HTTP {error.code}") from error
    except URLError as error:
        raise RerankerProviderError(f"reranker provider request failed: {error.reason}") from error
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RerankerProviderError("reranker provider returned invalid JSON") from error
    if not isinstance(body, dict):
        raise RerankerProviderError("reranker provider returned a non-object JSON body")
    if body.get("code") and body.get("code") != "200":
        raise RerankerProviderError(f"reranker provider error: {body.get('code')}")
    return body


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_")
