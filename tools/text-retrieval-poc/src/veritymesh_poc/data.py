from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, TypeVar

from .domain import ContractError, Document, QueryCase


T = TypeVar("T")


def load_documents(path: str | Path) -> list[Document]:
    documents = _load_jsonl(path, Document.from_dict)
    _ensure_unique(
        ((document.document_id, document.knowledge_revision_id) for document in documents),
        "document revision",
    )
    return documents


def load_queries(path: str | Path) -> list[QueryCase]:
    queries = _load_jsonl(path, QueryCase.from_dict)
    _ensure_unique(((query.query_id,) for query in queries), "query")
    return queries


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_jsonl(path: str | Path, factory: Callable[[dict], T]) -> list[T]:
    source = Path(path)
    if not source.is_file():
        raise ContractError(f"JSONL file does not exist: {source}")
    values: list[T] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ContractError("record must be a JSON object")
                values.append(factory(raw))
            except (json.JSONDecodeError, ContractError, TypeError, ValueError) as error:
                raise ContractError(f"{source}:{line_number}: {error}") from error
    if not values:
        raise ContractError(f"JSONL file has no records: {source}")
    return values


def _ensure_unique(keys, label: str) -> None:
    seen = set()
    for key in keys:
        if key in seen:
            raise ContractError(f"duplicate {label}: {'/'.join(key)}")
        seen.add(key)
