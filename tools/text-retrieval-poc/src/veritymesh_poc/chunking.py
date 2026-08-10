from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
from typing import Protocol

from .domain import Chunk, ContractError, Document, EmbeddingBatch
from .tokenization import OffsetTokenizer, TokenSpan, UnicodeRegexTokenizer


@dataclass(frozen=True)
class ChunkProfile:
    name: str
    target_tokens: int
    soft_min_tokens: int
    hard_max_tokens: int
    overlap_tokens: int
    keep_code_blocks: bool = False
    keep_tables: bool = False


DEFAULT_PROFILES = {
    "prose": ChunkProfile("prose-v1", 512, 256, 800, 64),
    "faq": ChunkProfile("faq-v1", 360, 96, 640, 0),
    "api": ChunkProfile("api-v1", 520, 180, 800, 48, keep_code_blocks=True),
    "release_notes": ChunkProfile("release-notes-v1", 420, 120, 700, 24),
    "policy": ChunkProfile("policy-clauses-v1", 480, 160, 760, 32),
    "table": ChunkProfile("table-v1", 320, 80, 640, 0, keep_tables=True),
    "code": ChunkProfile("code-v1", 560, 120, 800, 32, keep_code_blocks=True),
}


class DocumentEmbedder(Protocol):
    def embed_documents(self, texts: list[str]) -> EmbeddingBatch: ...


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    section: str
    kind: str


class BaseChunker:
    name = "base"
    version = "base-v1"

    def __init__(self, tokenizer: OffsetTokenizer | None = None):
        self.tokenizer = tokenizer or UnicodeRegexTokenizer()

    def chunk(self, document: Document) -> list[Chunk]:
        raise NotImplementedError

    def _profile(self, document: Document) -> ChunkProfile:
        return DEFAULT_PROFILES.get(document.document_type, DEFAULT_PROFILES["prose"])

    def _make(self, document: Document, section: str, start: int, end: int) -> Chunk:
        return Chunk.from_document(
            document,
            chunker_version=f"{self.version}:{self.tokenizer.fingerprint}:{self._profile(document).name}",
            section=section,
            start_char=start,
            end_char=end,
        )


class FixedRecursiveChunker(BaseChunker):
    name = "fixed_recursive"
    version = "fixed-recursive-v1"

    def chunk(self, document: Document) -> list[Chunk]:
        profile = self._profile(document)
        tokens = self.tokenizer.spans(document.text)
        if not tokens:
            return []
        window = min(profile.target_tokens, profile.hard_max_tokens)
        overlap = min(profile.overlap_tokens, max(0, window - 1))
        chunks: list[Chunk] = []
        offset = 0
        while offset < len(tokens):
            selected = tokens[offset : offset + window]
            start = selected[0].start
            end = selected[-1].end
            chunks.append(self._make(document, document.title, start, end))
            if offset + window >= len(tokens):
                break
            offset += window - overlap
        return chunks


class StructureAwareChunker(BaseChunker):
    name = "structure_aware"
    version = "structure-aware-v1"

    def chunk(self, document: Document) -> list[Chunk]:
        units = _markdown_units(document)
        if not units:
            return []
        profile = self._profile(document)
        expanded: list[_Unit] = []
        for unit in units:
            expanded.extend(self._split_oversized(document, unit, profile))

        chunks: list[Chunk] = []
        current: list[_Unit] = []
        current_tokens = 0
        for unit in expanded:
            unit_tokens = _unit_tokens(self.tokenizer, document, unit)
            section_changed = bool(current and current[-1].section != unit.section)
            exceeds_target = current and current_tokens + unit_tokens > profile.target_tokens
            if section_changed or (exceeds_target and current_tokens >= profile.soft_min_tokens):
                chunks.append(self._from_units(document, current))
                current = []
                current_tokens = 0
            if current and current_tokens + unit_tokens > profile.hard_max_tokens:
                chunks.append(self._from_units(document, current))
                current = []
                current_tokens = 0
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            chunks.append(self._from_units(document, current))
        return chunks

    def _split_oversized(self, document: Document, unit: _Unit, profile: ChunkProfile) -> list[_Unit]:
        spans = self.tokenizer.spans(document.text[unit.start : unit.end])
        if len(spans) <= profile.hard_max_tokens:
            return [unit]
        if (unit.kind == "code" and profile.keep_code_blocks) or (unit.kind == "table" and profile.keep_tables):
            # The hard limit wins over atomicity; an oversized block is still split at token offsets.
            pass
        overlap = min(profile.overlap_tokens, max(0, profile.hard_max_tokens - 1))
        pieces: list[_Unit] = []
        cursor = 0
        while cursor < len(spans):
            selected = spans[cursor : cursor + profile.hard_max_tokens]
            start = unit.start + selected[0].start
            end = unit.start + selected[-1].end
            pieces.append(_Unit(start, end, unit.section, unit.kind))
            if cursor + profile.hard_max_tokens >= len(spans):
                break
            cursor += profile.hard_max_tokens - overlap
        return pieces

    def _from_units(self, document: Document, units: list[_Unit]) -> Chunk:
        return self._make(document, units[0].section, units[0].start, units[-1].end)


class SemanticBoundaryChunker(BaseChunker):
    name = "semantic_boundary"
    version = "embedding-semantic-boundary-v1"

    def __init__(self, embedder: DocumentEmbedder, tokenizer: OffsetTokenizer | None = None):
        super().__init__(tokenizer)
        self.embedder = embedder

    def chunk(self, document: Document) -> list[Chunk]:
        profile = replace(self._profile(document), overlap_tokens=0)
        sentences = _sentence_units(document)
        if not sentences:
            return []
        texts = [document.text[unit.start : unit.end] for unit in sentences]
        batch = self.embedder.embed_documents(texts)
        if len(batch.vectors) != len(sentences):
            raise ContractError("semantic chunker received the wrong embedding count")
        similarities = [
            _cosine(batch.vectors[index - 1], batch.vectors[index])
            for index in range(1, len(batch.vectors))
        ]
        boundary = _quantile(similarities, 0.25) if similarities else -1.0

        chunks: list[Chunk] = []
        current: list[_Unit] = []
        current_tokens = 0
        for index, unit in enumerate(sentences):
            unit_tokens = _unit_tokens(self.tokenizer, document, unit)
            semantic_break = index > 0 and similarities[index - 1] <= boundary
            target_break = bool(current and current_tokens + unit_tokens > profile.target_tokens)
            if current and current_tokens >= profile.soft_min_tokens and (semantic_break or target_break):
                chunks.append(self._from_units(document, current))
                current = []
                current_tokens = 0
            if unit_tokens > profile.hard_max_tokens:
                splitter = StructureAwareChunker(self.tokenizer)
                long_units = splitter._split_oversized(document, unit, profile)
                if current:
                    chunks.append(self._from_units(document, current))
                    current = []
                    current_tokens = 0
                chunks.extend(self._from_units(document, [piece]) for piece in long_units)
                continue
            if current and current_tokens + unit_tokens > profile.hard_max_tokens:
                chunks.append(self._from_units(document, current))
                current = []
                current_tokens = 0
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            chunks.append(self._from_units(document, current))
        return chunks

    def _from_units(self, document: Document, units: list[_Unit]) -> Chunk:
        return self._make(document, units[0].section, units[0].start, units[-1].end)


_heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_fence = re.compile(r"^\s*(```|~~~)")
_table_separator = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")


def _markdown_units(document: Document) -> list[_Unit]:
    lines = document.text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    sections: list[str] = []
    units: list[_Unit] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.rstrip("\r\n")
        heading = _heading.match(stripped)
        if heading:
            level = len(heading.group(1))
            sections = sections[: level - 1]
            sections.append(heading.group(2).strip())
            index += 1
            continue
        if not stripped.strip():
            index += 1
            continue
        start_index = index
        kind = "paragraph"
        fence = _fence.match(stripped)
        if fence:
            kind = "code"
            marker = fence.group(1)
            index += 1
            while index < len(lines):
                if lines[index].lstrip().startswith(marker):
                    index += 1
                    break
                index += 1
        elif "|" in stripped and index + 1 < len(lines) and _table_separator.match(lines[index + 1].rstrip("\r\n")):
            kind = "table"
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                index += 1
        else:
            index += 1
            while index < len(lines):
                candidate = lines[index].rstrip("\r\n")
                if not candidate.strip() or _heading.match(candidate) or _fence.match(candidate):
                    break
                if "|" in candidate and index + 1 < len(lines) and _table_separator.match(lines[index + 1].rstrip("\r\n")):
                    break
                index += 1
        start = offsets[start_index]
        end = offsets[index] if index < len(offsets) else len(document.text)
        end = _trim_right(document.text, start, end)
        if end > start:
            units.append(_Unit(start, end, " / ".join(sections) or document.title, kind))
    return units


def _sentence_units(document: Document) -> list[_Unit]:
    pattern = re.compile(r".*?(?:[。！？!?；;]\s*|\n{2,}|$)", re.DOTALL)
    units: list[_Unit] = []
    for match in pattern.finditer(document.text):
        start, end = match.span()
        while start < end and document.text[start].isspace():
            start += 1
        end = _trim_right(document.text, start, end)
        if end > start:
            units.append(_Unit(start, end, document.title, "sentence"))
    return units


def _trim_right(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def _unit_tokens(tokenizer: OffsetTokenizer, document: Document, unit: _Unit) -> int:
    return len(tokenizer.spans(document.text[unit.start : unit.end]))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
