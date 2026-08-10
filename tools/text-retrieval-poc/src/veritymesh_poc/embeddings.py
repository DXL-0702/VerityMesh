from __future__ import annotations

from hashlib import sha256
import json
import math
import os
import struct
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .domain import ContractError, EmbeddingBatch, EmbeddingSpace
from .tokenization import OffsetTokenizer, UnicodeRegexTokenizer, count_tokens


class ProviderError(RuntimeError):
    """An external model call failed or returned an invalid contract."""


class EmbeddingAdapter:
    space: EmbeddingSpace

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        raise NotImplementedError

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        raise NotImplementedError


class DeterministicHashEmbedding(EmbeddingAdapter):
    """Local-only embedding used to validate harness behavior, never product quality."""

    def __init__(self, dimension: int = 128, seed: str = "veritymesh-harness-v1"):
        self.space = EmbeddingSpace(
            provider="local-harness",
            region="local",
            api_mode="deterministic",
            model="deterministic-hash-embedding",
            revision=seed,
            dimension=dimension,
            distance="cosine",
            normalized=True,
            normalization_version="l2-v1",
            role_encoding="local-prefix-v1",
            query_instruction="query:",
            document_instruction="document:",
            tokenizer_fingerprint="unicode-regex-offset-v1",
            truncation_policy_version="local-harness-no-truncation-v1",
            preprocessing_version="unicode-regex-token-v1",
        )
        self._tokenizer = UnicodeRegexTokenizer()
        self._seed = seed

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, self.space.document_instruction)

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, self.space.query_instruction)

    def _embed(self, texts: list[str], instruction: str) -> EmbeddingBatch:
        vectors = tuple(self._one(f"{instruction} {text}") for text in texts)
        return EmbeddingBatch(vectors=vectors, space=self.space)

    def _one(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.space.dimension
        for token in self._tokenizer.spans(text):
            digest = sha256(f"{self._seed}\x1f{token.text.lower()}".encode("utf-8")).digest()
            first = int.from_bytes(digest[:4], "big") % self.space.dimension
            second = int.from_bytes(digest[4:8], "big") % self.space.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[first] += sign
            vector[second] += sign * 0.5
        return _l2_normalize_float32(vector, self.space.dimension)


@dataclass(frozen=True)
class DashScopeEmbeddingConfig:
    model: str
    dimension: int = 1024
    region: str = "cn-beijing"
    api_key_env: str = "DASHSCOPE_API_KEY"
    endpoint: str = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    api_mode: str = "native"
    batch_size: int = 16
    timeout_seconds: float = 30.0
    revision: str = "configured"
    query_instruction: str = ""
    document_instruction: str = ""
    query_max_tokens: int = 512
    document_max_tokens: int = 1024


class DashScopeEmbeddingAdapter(EmbeddingAdapter):
    """DashScope adapter with native and OpenAI-compatible response parsing."""

    def __init__(self, config: DashScopeEmbeddingConfig, *, tokenizer: OffsetTokenizer):
        if config.api_mode not in {"native", "compatible"}:
            raise ContractError(f"unsupported DashScope embedding api_mode: {config.api_mode}")
        if config.query_max_tokens <= 0 or config.document_max_tokens <= 0:
            raise ContractError("embedding token limits must be positive")
        self.config = config
        self.tokenizer = tokenizer
        self.space = EmbeddingSpace(
            provider="aliyun-bailian",
            region=config.region,
            api_mode=config.api_mode,
            model=config.model,
            revision=config.revision,
            dimension=config.dimension,
            distance="cosine",
            normalized=True,
            normalization_version="l2-v1",
            role_encoding="native-text-type-v1" if config.api_mode == "native" else "compatible-input-v1",
            query_instruction=config.query_instruction,
            document_instruction=config.document_instruction,
            tokenizer_fingerprint=tokenizer.fingerprint,
            truncation_policy_version=(
                f"document-{config.document_max_tokens}-query-{config.query_max_tokens}-no-silent-truncation-v1"
            ),
            preprocessing_version="dashscope-request-v2",
        )

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, "document")

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, "query")

    def _embed(self, texts: list[str], text_type: str) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch((), self.space)
        vectors: list[tuple[float, ...]] = []
        instruction = (
            self.config.query_instruction if text_type == "query" else self.config.document_instruction
        )
        prepared = [f"{instruction}{text}" if instruction else text for text in texts]
        token_limit = self.config.query_max_tokens if text_type == "query" else self.config.document_max_tokens
        for text in prepared:
            token_count = count_tokens(self.tokenizer, text)
            if token_count > token_limit:
                raise ContractError(
                    f"{text_type} embedding input exceeds {token_limit} tokens: {token_count}; silent truncation is forbidden"
                )
        for batch in _batches(prepared, self.config.batch_size):
            payload = self._payload(batch, text_type)
            body = _post_json(
                self.config.endpoint,
                payload,
                api_key=_required_api_key(self.config.api_key_env),
                timeout=self.config.timeout_seconds,
            )
            vectors.extend(self._parse(body, expected=len(batch)))
        result = EmbeddingBatch(tuple(vectors), self.space)
        return result

    def _payload(self, texts: list[str], text_type: str) -> dict[str, Any]:
        if self.config.api_mode == "compatible":
            return {
                "model": self.config.model,
                "input": texts,
                "dimensions": self.config.dimension,
                "encoding_format": "float",
            }
        return {
            "model": self.config.model,
            "input": {"texts": texts},
            "parameters": {
                "dimension": self.config.dimension,
                "text_type": text_type,
            },
        }

    def _parse(self, body: dict[str, Any], *, expected: int) -> list[tuple[float, ...]]:
        output = body.get("output") if isinstance(body, dict) else None
        candidates = None
        if isinstance(output, dict):
            candidates = output.get("embeddings") or output.get("data")
        if candidates is None:
            candidates = body.get("data") if isinstance(body, dict) else None
        if not isinstance(candidates, list) or len(candidates) != expected:
            raise ProviderError("DashScope embedding response count does not match request")
        ordered: list[tuple[int, tuple[float, ...]]] = []
        for position, item in enumerate(candidates):
            raw = item.get("embedding") if isinstance(item, dict) else item
            index = int(item.get("index", position)) if isinstance(item, dict) else position
            if not isinstance(raw, list):
                raise ProviderError("DashScope embedding response has no vector")
            vector = _l2_normalize_float32(raw, self.config.dimension)
            ordered.append((index, vector))
        ordered.sort(key=lambda pair: pair[0])
        return [vector for _, vector in ordered]


def _batches(values: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ContractError("batch_size must be positive")
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _l2_normalize_float32(raw: Iterable[float], expected_dimension: int) -> tuple[float, ...]:
    values = [float(value) for value in raw]
    if len(values) != expected_dimension:
        raise ProviderError(
            f"embedding dimension mismatch: expected {expected_dimension}, got {len(values)}"
        )
    if any(not math.isfinite(value) for value in values):
        raise ProviderError("embedding vector contains a non-finite value")
    norm = math.sqrt(math.fsum(value * value for value in values))
    if norm <= 0.0:
        raise ProviderError("embedding vector has zero L2 norm")
    normalized = [_float32(value / norm) for value in values]
    rounded_norm = math.sqrt(math.fsum(value * value for value in normalized))
    if rounded_norm <= 0.0:
        raise ProviderError("embedding vector collapsed to zero after float32 conversion")
    return tuple(_float32(value / rounded_norm) for value in normalized)


def _float32(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


def _required_api_key(environment_name: str) -> str:
    value = os.environ.get(environment_name)
    if not value:
        raise ProviderError(f"missing required credential environment variable: {environment_name}")
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
        raise ProviderError(f"model provider returned HTTP {error.code}") from error
    except URLError as error:
        raise ProviderError(f"model provider request failed: {error.reason}") from error
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderError("model provider returned invalid JSON") from error
    if not isinstance(body, dict):
        raise ProviderError("model provider returned a non-object JSON body")
    if body.get("code") and body.get("code") != "200":
        raise ProviderError(f"model provider error: {body.get('code')}")
    return body
