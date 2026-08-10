from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Protocol


@dataclass(frozen=True)
class TokenSpan:
    text: str
    start: int
    end: int


class OffsetTokenizer(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def spans(self, text: str) -> list[TokenSpan]: ...


class UnicodeRegexTokenizer:
    """Deterministic fallback used only for harness and boundary validation."""

    _pattern = re.compile(
        r"[A-Za-z0-9_]+(?:[./:@+-][A-Za-z0-9_]+)*|[\u3400-\u4dbf\u4e00-\u9fff]|[^\s]",
        re.UNICODE,
    )

    @property
    def fingerprint(self) -> str:
        return "unicode-regex-offset-v1"

    def spans(self, text: str) -> list[TokenSpan]:
        return [TokenSpan(match.group(0), match.start(), match.end()) for match in self._pattern.finditer(text)]


class HuggingFaceOffsetTokenizer:
    """Pinned fast tokenizer for cloud-quality Chunk evaluation."""

    def __init__(
        self,
        pretrained_name_or_path: str,
        *,
        revision: str,
        local_files_only: bool = True,
        trust_remote_code: bool = False,
    ):
        if not revision or revision.lower() in {"latest", "main", "default", "pin-at-run-time"}:
            raise ValueError("tokenizer revision must be immutable and explicit")
        if not local_files_only:
            raise ValueError("production tokenizer must load from a pinned local artifact")
        if trust_remote_code:
            raise ValueError("production tokenizer must not execute remote code")
        try:
            from transformers import AutoTokenizer
        except ImportError as error:
            raise RuntimeError("install the tokenizer optional dependency to run the cloud matrix") from error
        self._tokenizer = AutoTokenizer.from_pretrained(
            pretrained_name_or_path,
            revision=revision,
            local_files_only=local_files_only,
            trust_remote_code=trust_remote_code,
            use_fast=True,
        )
        if not getattr(self._tokenizer, "is_fast", False):
            raise RuntimeError("cloud Chunk evaluation requires a fast tokenizer with offset mappings")
        backend = getattr(self._tokenizer, "backend_tokenizer", None)
        serialized = backend.to_str() if backend is not None else repr(self._tokenizer.get_vocab())
        self._fingerprint = "huggingface-offset:" + sha256(
            f"{pretrained_name_or_path}\x1f{revision}\x1f{serialized}".encode("utf-8")
        ).hexdigest()

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def spans(self, text: str) -> list[TokenSpan]:
        encoded = self._tokenizer(
            text,
            add_special_tokens=False,
            return_attention_mask=False,
            return_token_type_ids=False,
            return_offsets_mapping=True,
        )
        input_ids = encoded["input_ids"]
        offsets = encoded["offset_mapping"]
        tokens = self._tokenizer.convert_ids_to_tokens(input_ids)
        return [
            TokenSpan(str(token), int(start), int(end))
            for token, (start, end) in zip(tokens, offsets, strict=True)
            if int(end) > int(start)
        ]


def count_tokens(tokenizer: OffsetTokenizer, text: str) -> int:
    return len(tokenizer.spans(text))
