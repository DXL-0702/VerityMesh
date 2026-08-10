from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import math
from typing import Any, Mapping, Sequence


class ContractError(ValueError):
    """Raised when PoC input or a serving invariant is invalid."""


class EvidenceLevel(StrEnum):
    HARNESS_VALIDATION = "HARNESS_VALIDATION"
    LOCAL_CONTRACT = "LOCAL_CONTRACT"
    CLOUD_PRODUCT = "CLOUD_PRODUCT"


@dataclass(frozen=True)
class Document:
    document_id: str
    knowledge_revision_id: str
    project_id: str
    project_version: str
    locale: str
    access_segment: str
    knowledge_release_id: str
    knowledge_space_id: str
    citation_url: str
    title: str
    text: str
    document_type: str = "prose"
    effective_from: str | None = None
    effective_to: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Document":
        required = (
            "document_id",
            "knowledge_revision_id",
            "project_id",
            "project_version",
            "locale",
            "access_segment",
            "knowledge_release_id",
            "knowledge_space_id",
            "citation_url",
            "title",
            "text",
        )
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ContractError(f"document missing required fields: {', '.join(missing)}")
        text = str(raw["text"])
        if not text.strip():
            raise ContractError("document text must not be blank")
        known = set(required) | {"document_type", "effective_from", "effective_to", "metadata"}
        metadata = dict(raw.get("metadata") or {})
        metadata.update({key: value for key, value in raw.items() if key not in known})
        return cls(
            **{key: str(raw[key]) for key in required},
            document_type=str(raw.get("document_type", "prose")),
            effective_from=_optional_str(raw.get("effective_from")),
            effective_to=_optional_str(raw.get("effective_to")),
            metadata=metadata,
        )


@dataclass(frozen=True)
class QueryCase:
    query_id: str
    text: str
    project_id: str
    project_version: str
    locale: str
    allowed_access_segments: tuple[str, ...]
    knowledge_release_id: str
    relevant_documents: Mapping[str, int]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "QueryCase":
        required = (
            "query_id",
            "text",
            "project_id",
            "project_version",
            "locale",
            "allowed_access_segments",
            "knowledge_release_id",
            "relevant_documents",
        )
        missing = [key for key in required if key not in raw]
        if missing:
            raise ContractError(f"query missing required fields: {', '.join(missing)}")
        segments = raw["allowed_access_segments"]
        if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)) or not segments:
            raise ContractError("allowed_access_segments must be a non-empty array")
        qrels = raw["relevant_documents"]
        if isinstance(qrels, Sequence) and not isinstance(qrels, (str, bytes)):
            relevant = {str(document_id): 1 for document_id in qrels}
        elif isinstance(qrels, Mapping):
            relevant = {str(document_id): int(grade) for document_id, grade in qrels.items()}
        else:
            raise ContractError("relevant_documents must be an array or object")
        if any(grade < 0 for grade in relevant.values()):
            raise ContractError("relevance grades must be non-negative")
        return cls(
            query_id=str(raw["query_id"]),
            text=str(raw["text"]),
            project_id=str(raw["project_id"]),
            project_version=str(raw["project_version"]),
            locale=str(raw["locale"]),
            allowed_access_segments=tuple(str(value) for value in segments),
            knowledge_release_id=str(raw["knowledge_release_id"]),
            relevant_documents=relevant,
        )


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    chunker_version: str
    document_id: str
    knowledge_revision_id: str
    project_id: str
    project_version: str
    locale: str
    access_segment: str
    knowledge_release_id: str
    knowledge_space_id: str
    citation_url: str
    title: str
    section: str
    text: str
    start_char: int
    end_char: int
    effective_from: str | None = None
    effective_to: str | None = None

    @property
    def search_text(self) -> str:
        parts = [self.title]
        if self.section and self.section != self.title:
            parts.append(self.section)
        parts.append(self.text)
        return "\n".join(parts)

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        chunker_version: str,
        section: str,
        start_char: int,
        end_char: int,
    ) -> "Chunk":
        if not (0 <= start_char < end_char <= len(document.text)):
            raise ContractError(
                f"invalid citation range for {document.document_id}: {start_char}:{end_char}"
            )
        text = document.text[start_char:end_char]
        digest = sha256(
            "\x1f".join(
                (
                    document.knowledge_revision_id,
                    chunker_version,
                    str(start_char),
                    str(end_char),
                    sha256(text.encode("utf-8")).hexdigest(),
                )
            ).encode("utf-8")
        ).hexdigest()[:24]
        return cls(
            chunk_id=f"chk_{digest}",
            chunker_version=chunker_version,
            document_id=document.document_id,
            knowledge_revision_id=document.knowledge_revision_id,
            project_id=document.project_id,
            project_version=document.project_version,
            locale=document.locale,
            access_segment=document.access_segment,
            knowledge_release_id=document.knowledge_release_id,
            knowledge_space_id=document.knowledge_space_id,
            citation_url=document.citation_url,
            title=document.title,
            section=section or document.title,
            text=text,
            start_char=start_char,
            end_char=end_char,
            effective_from=document.effective_from,
            effective_to=document.effective_to,
        )


@dataclass(frozen=True)
class EmbeddingSpace:
    provider: str
    region: str
    api_mode: str
    model: str
    revision: str
    dimension: int
    distance: str
    normalized: bool
    normalization_version: str
    role_encoding: str
    query_instruction: str
    document_instruction: str
    tokenizer_fingerprint: str
    truncation_policy_version: str
    preprocessing_version: str

    def __post_init__(self) -> None:
        if self.dimension <= 0:
            raise ContractError("embedding dimension must be positive")
        if self.distance not in {"cosine", "dot_product"}:
            raise ContractError(f"unsupported embedding distance: {self.distance}")

    @property
    def fingerprint(self) -> str:
        value = "\x1f".join(
            (
                self.provider,
                self.region,
                self.api_mode,
                self.model,
                self.revision,
                str(self.dimension),
                self.distance,
                str(self.normalized),
                self.normalization_version,
                self.role_encoding,
                self.query_instruction,
                self.document_instruction,
                self.tokenizer_fingerprint,
                self.truncation_policy_version,
                self.preprocessing_version,
            )
        )
        return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    space: EmbeddingSpace

    def __post_init__(self) -> None:
        for vector in self.vectors:
            if len(vector) != self.space.dimension:
                raise ContractError(
                    f"embedding dimension mismatch: expected {self.space.dimension}, got {len(vector)}"
                )
            if any(not math.isfinite(value) for value in vector):
                raise ContractError("embedding vector contains a non-finite value")
            if self.space.normalized:
                norm = math.sqrt(math.fsum(value * value for value in vector))
                if not 0.999 <= norm <= 1.001:
                    raise ContractError(f"embedding vector is not L2-normalized: norm={norm}")


@dataclass(frozen=True)
class IndexedChunk:
    chunk: Chunk
    vector: tuple[float, ...]
    embedding_space_fingerprint: str
    configuration_id: str


@dataclass(frozen=True)
class SearchScope:
    project_id: str
    project_version: str
    locale: str
    allowed_access_segments: tuple[str, ...]
    knowledge_release_id: str
    configuration_id: str
    now: str | None = None


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float
    rank: int
    source: str
    lexical_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
