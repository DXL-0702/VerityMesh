"""Provider-neutral generation contracts and unvalidated claim buffering."""

from __future__ import annotations

import asyncio
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from .execution_context import (
    AuditContext,
    Clock,
    ExecutionContextGuard,
    ExecutionDeadlineExceeded,
    FrozenStrictModel,
    GuardedExecutionContext,
    Identifier,
    utc_now,
)
from .prompt_builder import Prompt, PromptMode
from .retrieval import Sha256Digest
from .revocation import (
    RevocationClearedExecutionContext,
    revalidate_cleared_execution_context,
)

GeneratedChunkText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=131_072),
]
GeneratedFullText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=2_000_000),
]
NonNegativeInteger = Annotated[int, Field(ge=0, strict=True)]
MAX_CLAIM_BUFFER_CHARACTERS = 2_000_000


class GenerationMode(StrEnum):
    GENERATED = "GENERATED"
    FALLBACK_GENERATED = "FALLBACK_GENERATED"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    REFUSAL = "REFUSAL"
    EMPTY = "EMPTY"


class GenerationDegradationReason(StrEnum):
    NONE = "NONE"
    GENERATOR_UNAVAILABLE = "GENERATOR_UNAVAILABLE"
    GENERATOR_CONTRACT_REJECTED = "GENERATOR_CONTRACT_REJECTED"
    FALLBACK_UNAVAILABLE = "FALLBACK_UNAVAILABLE"
    FALLBACK_CONTRACT_REJECTED = "FALLBACK_CONTRACT_REJECTED"
    NO_EVIDENCE = "NO_EVIDENCE"


class GenerationFinishReason(StrEnum):
    STOP = "STOP"
    LENGTH = "LENGTH"
    CONTENT_FILTER = "CONTENT_FILTER"


class GeneratedValidationStatus(StrEnum):
    UNVALIDATED = "UNVALIDATED"


class GeneratorBinding(FrozenStrictModel):
    """Trusted logical and physical identity resolved by server policy."""

    logical_model: Literal["generator-primary"]
    provider: Identifier
    region: Identifier
    api_mode: Identifier
    model: Identifier
    revision: Identifier
    configuration_fingerprint: Sha256Digest


class GeneratedTextChunk(FrozenStrictModel):
    """One ordered provider-neutral text fragment, still unvalidated."""

    sequence: Annotated[int, Field(ge=1, strict=True)]
    text: GeneratedChunkText

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        _validate_text_controls(value)
        return value


class GeneratorUsage(FrozenStrictModel):
    """Provider usage normalized before it reaches audit or cost accounting."""

    input_tokens: NonNegativeInteger
    output_tokens: NonNegativeInteger
    total_tokens: NonNegativeInteger

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("generator usage total must equal input plus output tokens")
        return self


class GeneratorRequest(FrozenStrictModel):
    """Minimal request exposed to a Model Access Provider adapter."""

    prompt: Prompt
    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    binding: GeneratorBinding
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext

    @field_validator("deadline_at")
    @classmethod
    def normalize_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generator deadline must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.message_execution_id != self.prompt.message_execution_id:
            raise ValueError("generator request execution ID must match the prompt")
        if self.prompt_fingerprint != self.prompt.prompt_fingerprint:
            raise ValueError("generator request fingerprint must match the prompt")
        if self.deadline_remaining <= timedelta(0):
            raise ValueError("generator request deadline must remain positive")
        return self


class GeneratorResult(FrozenStrictModel):
    """Provider response before it is admitted into the generation result."""

    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    binding: GeneratorBinding
    chunks: tuple[GeneratedTextChunk, ...]
    finish_reason: GenerationFinishReason
    usage: GeneratorUsage
    validation_status: Literal["UNVALIDATED"] = "UNVALIDATED"

    @property
    def segments(self) -> tuple[GeneratedTextChunk, ...]:
        return self.chunks

    @model_validator(mode="after")
    def validate_chunks(self) -> Self:
        if len(self.chunks) > 1_024:
            raise ValueError("generator output cannot exceed 1024 chunks")
        if tuple(item.sequence for item in self.chunks) != tuple(range(1, len(self.chunks) + 1)):
            raise ValueError("generator chunk sequences must be contiguous and start at one")
        if sum(len(item.text) for item in self.chunks) > 2_000_000:
            raise ValueError("generator output exceeds the maximum text size")
        return self


class GeneratorPort(Protocol):
    """Task-semantic port; Provider SDK and framework types stay behind adapters."""

    async def generate(self, request: GeneratorRequest) -> GeneratorResult: ...


class GeneratedText(FrozenStrictModel):
    """Complete model output retained for later grounding, never as a validated claim."""

    chunks: tuple[GeneratedTextChunk, ...]
    validation_status: Literal["UNVALIDATED"] = "UNVALIDATED"

    @property
    def text(self) -> str:
        return "".join(item.text for item in self.chunks)

    @model_validator(mode="after")
    def validate_chunks(self) -> Self:
        if not self.chunks:
            raise ValueError("generated text requires at least one chunk")
        if tuple(item.sequence for item in self.chunks) != tuple(range(1, len(self.chunks) + 1)):
            raise ValueError("generated text chunk sequences must be contiguous and start at one")
        if sum(len(item.text) for item in self.chunks) > MAX_CLAIM_BUFFER_CHARACTERS:
            raise ValueError("generated text exceeds the maximum text size")
        return self


class CandidateClaim(FrozenStrictModel):
    """A complete sentence candidate that still awaits Grounding validation."""

    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    claim_id: Identifier
    sequence: Annotated[int, Field(ge=1, strict=True)]
    text: GeneratedFullText
    validation_status: Literal["UNVALIDATED"] = "UNVALIDATED"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        _validate_text_controls(value)
        return value


class GenerationResult(FrozenStrictModel):
    """Generation outcome with explicit output and degradation semantics."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    mode: GenerationMode
    degradation_reason: GenerationDegradationReason
    binding: GeneratorBinding | None
    text: GeneratedText | None
    finish_reason: GenerationFinishReason | None
    usage: GeneratorUsage | None

    @property
    def generated_text(self) -> str | None:
        return None if self.text is None else self.text.text

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        model_output = self.mode in (
            GenerationMode.GENERATED,
            GenerationMode.FALLBACK_GENERATED,
        )
        empty_output = self.mode is GenerationMode.EMPTY
        if model_output or empty_output:
            if self.binding is None or self.finish_reason is None or self.usage is None:
                raise ValueError("model generation modes require binding, finish reason and usage")
        else:
            if self.binding is not None or self.finish_reason is not None or self.usage is not None:
                raise ValueError("non-model generation modes cannot claim a provider call")

        if model_output:
            if self.text is None:
                raise ValueError("generated modes require unvalidated text")
            if self.mode is GenerationMode.GENERATED and (
                self.degradation_reason is not GenerationDegradationReason.NONE
            ):
                raise ValueError("primary generated output cannot claim degradation")
            if self.mode is GenerationMode.FALLBACK_GENERATED and self.degradation_reason in (
                GenerationDegradationReason.NONE,
                GenerationDegradationReason.NO_EVIDENCE,
                GenerationDegradationReason.FALLBACK_UNAVAILABLE,
                GenerationDegradationReason.FALLBACK_CONTRACT_REJECTED,
            ):
                raise ValueError("fallback generated output must preserve the primary failure")
        elif self.text is not None:
            raise ValueError("non-generated modes cannot contain model text")

        if self.mode is GenerationMode.REFUSAL and (
            self.degradation_reason is not GenerationDegradationReason.NO_EVIDENCE
        ):
            raise ValueError("refusal mode requires the no-evidence reason")
        elif self.mode is GenerationMode.EVIDENCE_ONLY and self.degradation_reason in (
            GenerationDegradationReason.NONE,
            GenerationDegradationReason.NO_EVIDENCE,
        ):
            raise ValueError("evidence-only mode requires a provider degradation reason")
        return self


class GenerationRejected(RuntimeError):
    code = "generation_rejected"


class GenerationInputRejected(GenerationRejected):
    code = "generation_input_rejected"


class GenerationScopeRejected(GenerationRejected):
    code = "generation_scope_rejected"


class ClaimBufferRejected(RuntimeError):
    code = "claim_buffer_rejected"


class ClaimBufferSequenceRejected(ClaimBufferRejected):
    code = "claim_buffer_sequence_rejected"


class ClaimBufferClosed(ClaimBufferRejected):
    code = "claim_buffer_closed"


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    context: RevocationClearedExecutionContext
    prompt: Prompt
    binding: GeneratorBinding
    fallback_binding: GeneratorBinding | None = None


class ClaimBuffer:
    """Buffers complete sentence candidates without assigning Evidence support."""

    def __init__(self, *, message_execution_id: str, prompt_fingerprint: str) -> None:
        self._message_execution_id = message_execution_id
        self._prompt_fingerprint = prompt_fingerprint
        self._pending = ""
        self._next_chunk_sequence = 1
        self._next_claim_sequence = 1
        self._closed = False

    @property
    def pending_text(self) -> str:
        return self._pending

    def append(self, chunk: GeneratedTextChunk) -> tuple[CandidateClaim, ...]:
        if self._closed:
            raise ClaimBufferClosed("claim buffer is already closed")
        if not isinstance(chunk, GeneratedTextChunk):
            raise ClaimBufferSequenceRejected("claim buffer requires a GeneratedTextChunk")
        if chunk.sequence != self._next_chunk_sequence:
            raise ClaimBufferSequenceRejected("generated chunks must arrive in order exactly once")
        if len(self._pending) + len(chunk.text) > MAX_CLAIM_BUFFER_CHARACTERS:
            raise ClaimBufferRejected("claim buffer exceeds the maximum text size")
        self._next_chunk_sequence += 1
        scan_from = len(self._pending)
        self._pending += chunk.text
        claims: list[CandidateClaim] = []
        start = 0
        for index in range(scan_from, len(self._pending)):
            character = self._pending[index]
            if character in "\u3002\uff01\uff1f!?.\n":
                candidate_text = self._pending[start : index + 1].strip()
                if candidate_text:
                    claims.append(self._claim(candidate_text))
                start = index + 1
        self._pending = self._pending[start:]
        return tuple(claims)

    def flush(self) -> tuple[CandidateClaim, ...]:
        if self._closed:
            return ()
        self._closed = True
        candidate_text = self._pending.strip()
        self._pending = ""
        if not candidate_text:
            return ()
        return (self._claim(candidate_text),)

    def _claim(self, text: str) -> CandidateClaim:
        sequence = self._next_claim_sequence
        self._next_claim_sequence += 1
        return CandidateClaim(
            message_execution_id=self._message_execution_id,
            prompt_fingerprint=self._prompt_fingerprint,
            claim_id=f"claim-{sequence}",
            sequence=sequence,
            text=text,
        )


class GenerationKernel:
    """Calls at most one primary and one fallback Provider under one deadline."""

    def __init__(
        self,
        port: GeneratorPort,
        *,
        fallback_port: GeneratorPort | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._port = port
        self._fallback_port = fallback_port or port
        self._context_guard = ExecutionContextGuard(clock)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        current, validated = self._validate_request(request)
        prompt = validated.prompt
        if prompt.mode is PromptMode.REFUSAL:
            return _non_model_result(
                prompt,
                mode=GenerationMode.REFUSAL,
                reason=GenerationDegradationReason.NO_EVIDENCE,
            )

        try:
            primary_request = self._provider_request(current, prompt, validated.binding)
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise GenerationScopeRejected from error
        try:
            async with asyncio.timeout(primary_request.deadline_remaining.total_seconds()):
                raw_result = await self._port.generate(primary_request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except TimeoutError:
            self._validate_context(validated.context)
            return await self._fallback_or_evidence_only(
                validated,
                primary_reason=GenerationDegradationReason.GENERATOR_UNAVAILABLE,
            )
        except Exception:
            self._validate_context(validated.context)
            return await self._fallback_or_evidence_only(
                validated,
                primary_reason=GenerationDegradationReason.GENERATOR_UNAVAILABLE,
            )

        self._validate_context(validated.context)
        try:
            result = GeneratorResult.model_validate(raw_result.model_dump())
            self._validate_provider_result(result, primary_request)
        except (AttributeError, TypeError, ValueError, ValidationError):
            self._validate_context(validated.context)
            return await self._fallback_or_evidence_only(
                validated,
                primary_reason=GenerationDegradationReason.GENERATOR_CONTRACT_REJECTED,
            )
        return _model_result(
            prompt,
            result,
            mode=(GenerationMode.GENERATED if result.chunks else GenerationMode.EMPTY),
            reason=GenerationDegradationReason.NONE,
        )

    def _provider_request(
        self,
        current: GuardedExecutionContext,
        prompt: Prompt,
        binding: GeneratorBinding,
    ) -> GeneratorRequest:
        return GeneratorRequest(
            prompt=prompt,
            message_execution_id=prompt.message_execution_id,
            prompt_fingerprint=prompt.prompt_fingerprint,
            binding=binding,
            deadline_at=current.context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=current.context.audit,
        )

    async def _fallback_or_evidence_only(
        self,
        request: GenerationRequest,
        *,
        primary_reason: GenerationDegradationReason,
    ) -> GenerationResult:
        if request.fallback_binding is None:
            return _non_model_result(
                request.prompt,
                mode=GenerationMode.EVIDENCE_ONLY,
                reason=primary_reason,
            )
        current = self._validate_context(request.context)
        try:
            fallback_request = self._provider_request(
                current,
                request.prompt,
                request.fallback_binding,
            )
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise GenerationScopeRejected from error
        try:
            async with asyncio.timeout(fallback_request.deadline_remaining.total_seconds()):
                raw_result = await self._fallback_port.generate(fallback_request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except TimeoutError:
            self._validate_context(request.context)
            return _non_model_result(
                request.prompt,
                mode=GenerationMode.EVIDENCE_ONLY,
                reason=GenerationDegradationReason.FALLBACK_UNAVAILABLE,
            )
        except Exception:
            self._validate_context(request.context)
            return _non_model_result(
                request.prompt,
                mode=GenerationMode.EVIDENCE_ONLY,
                reason=GenerationDegradationReason.FALLBACK_UNAVAILABLE,
            )

        self._validate_context(request.context)
        try:
            result = GeneratorResult.model_validate(raw_result.model_dump())
            self._validate_provider_result(result, fallback_request)
        except (AttributeError, TypeError, ValueError, ValidationError):
            self._validate_context(request.context)
            return _non_model_result(
                request.prompt,
                mode=GenerationMode.EVIDENCE_ONLY,
                reason=GenerationDegradationReason.FALLBACK_CONTRACT_REJECTED,
            )
        return _model_result(
            request.prompt,
            result,
            mode=(GenerationMode.FALLBACK_GENERATED if result.chunks else GenerationMode.EMPTY),
            reason=primary_reason,
        )

    def _validate_request(
        self,
        request: GenerationRequest,
    ) -> tuple[GuardedExecutionContext, GenerationRequest]:
        if not isinstance(request, GenerationRequest):
            raise GenerationInputRejected("generation kernel requires a GenerationRequest")
        if not isinstance(request.context, RevocationClearedExecutionContext):
            raise GenerationInputRejected("generation request requires a cleared execution context")
        current = self._validate_context(request.context)
        try:
            prompt = Prompt.model_validate(request.prompt.model_dump())
            binding = GeneratorBinding.model_validate(request.binding.model_dump())
            fallback_binding = (
                None
                if request.fallback_binding is None
                else GeneratorBinding.model_validate(request.fallback_binding.model_dump())
            )
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise GenerationInputRejected from error
        if fallback_binding is not None and fallback_binding == binding:
            raise GenerationInputRejected("primary and fallback bindings must differ")
        context = request.context.context
        if (
            prompt.message_execution_id != context.message_execution_id
            or prompt.project_id != context.project_id
            or prompt.project_version != context.project_version
            or prompt.locale != context.locale
            or prompt.knowledge_release_id != context.knowledge_release_id
        ):
            raise GenerationScopeRejected("prompt does not match the execution context")
        return current, GenerationRequest(
            context=request.context,
            prompt=prompt,
            binding=binding,
            fallback_binding=fallback_binding,
        )

    def _validate_context(
        self,
        context: RevocationClearedExecutionContext,
    ) -> GuardedExecutionContext:
        return revalidate_cleared_execution_context(context, self._context_guard)

    @staticmethod
    def _validate_provider_result(result: GeneratorResult, request: GeneratorRequest) -> None:
        if result.message_execution_id != request.message_execution_id:
            raise ValueError("generator result execution ID does not match the request")
        if result.prompt_fingerprint != request.prompt_fingerprint:
            raise ValueError("generator result fingerprint does not match the request")
        if result.binding != request.binding:
            raise ValueError("generator result binding does not match the request")


def _model_result(
    prompt: Prompt,
    provider_result: GeneratorResult,
    *,
    mode: GenerationMode,
    reason: GenerationDegradationReason,
) -> GenerationResult:
    text = GeneratedText(chunks=provider_result.chunks) if provider_result.chunks else None
    return GenerationResult(
        schema_version="1.0",
        message_execution_id=prompt.message_execution_id,
        prompt_fingerprint=prompt.prompt_fingerprint,
        mode=mode,
        degradation_reason=reason,
        binding=provider_result.binding,
        text=text,
        finish_reason=provider_result.finish_reason,
        usage=provider_result.usage,
    )


def _non_model_result(
    prompt: Prompt,
    *,
    mode: GenerationMode,
    reason: GenerationDegradationReason,
) -> GenerationResult:
    return GenerationResult(
        schema_version="1.0",
        message_execution_id=prompt.message_execution_id,
        prompt_fingerprint=prompt.prompt_fingerprint,
        mode=mode,
        degradation_reason=reason,
        binding=None,
        text=None,
        finish_reason=None,
        usage=None,
    )


def _validate_text_controls(value: str) -> None:
    for character in value:
        if unicodedata.category(character) == "Cc" and character not in "\t\n\r":
            raise ValueError("generated text contains a control character")
