import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from test_prompt_builder import build_request
from veritymesh_assistant_runtime.execution_context import (
    ExecutionContextGuard,
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.generation import (
    CandidateClaim,
    ClaimBuffer,
    ClaimBufferClosed,
    ClaimBufferRejected,
    ClaimBufferSequenceRejected,
    GeneratedText,
    GeneratedTextChunk,
    GeneratedValidationStatus,
    GenerationDegradationReason,
    GenerationFinishReason,
    GenerationInputRejected,
    GenerationKernel,
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GenerationScopeRejected,
    GeneratorBinding,
    GeneratorRequest,
    GeneratorResult,
    GeneratorUsage,
)
from veritymesh_assistant_runtime.prompt_builder import PromptBuilder, PromptMode
from veritymesh_assistant_runtime.revocation import (
    RevocationClearedExecutionContext,
    RevocationScope,
)

CONFIGURATION_FINGERPRINT = "6" * 64


class ScriptedGenerator:
    def __init__(self, outcomes: list[GeneratorResult | Exception | object]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[GeneratorRequest] = []

    async def generate(self, request: GeneratorRequest) -> GeneratorResult:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return cast(GeneratorResult, outcome)


class DumpingGeneratorResult:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def model_dump(self) -> dict[str, object]:
        return self.values


class MissingDump:
    pass


def binding(revision: str = "generator-revision-1") -> GeneratorBinding:
    return GeneratorBinding(
        logical_model="generator-primary",
        provider="aliyun-bailian",
        region="cn-beijing",
        api_mode="native",
        model="qwen3.8-max",
        revision=revision,
        configuration_fingerprint=CONFIGURATION_FINGERPRINT,
    )


def cleared_context(
    context_factory: Callable[..., ProjectExecutionContext],
) -> RevocationClearedExecutionContext:
    guarded = ExecutionContextGuard(lambda: NOW).validate(context_factory())
    return RevocationClearedExecutionContext(
        guarded_context=guarded,
        revocation_scope=RevocationScope.from_context(guarded.context),
        revocation_snapshot_version="revocation-snapshot-7",
        revocation_checked_at=NOW,
        revocation_valid_until=NOW + timedelta(seconds=10),
    )


def generation_request(
    context_factory: Callable[..., ProjectExecutionContext],
    *,
    empty: bool = False,
    fallback_binding: GeneratorBinding | None = None,
    **prompt_overrides: Any,
) -> GenerationRequest:
    prompt_request = build_request(context_factory, empty=empty, **prompt_overrides)
    prompt = PromptBuilder(clock=lambda: NOW).build(prompt_request)
    return GenerationRequest(
        context=prompt_request.context,
        prompt=prompt,
        binding=binding(),
        fallback_binding=fallback_binding,
    )


def provider_result(
    request: GeneratorRequest,
    *chunks: str,
    binding_override: GeneratorBinding | None = None,
) -> GeneratorResult:
    return GeneratorResult(
        message_execution_id=request.message_execution_id,
        prompt_fingerprint=request.prompt_fingerprint,
        binding=binding_override or request.binding,
        chunks=tuple(
            GeneratedTextChunk(sequence=sequence, text=text)
            for sequence, text in enumerate(chunks, start=1)
        ),
        finish_reason=GenerationFinishReason.STOP,
        usage=GeneratorUsage(
            input_tokens=request.prompt.estimated_token_count,
            output_tokens=sum(len(text) for text in chunks),
            total_tokens=request.prompt.estimated_token_count + sum(len(text) for text in chunks),
        ),
    )


def test_primary_generation_is_provider_neutral_and_unvalidated(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = generation_request(context_factory)
    port = ScriptedGenerator([])
    expected = provider_result(
        GeneratorRequest(
            prompt=request.prompt,
            message_execution_id=request.prompt.message_execution_id,
            prompt_fingerprint=request.prompt.prompt_fingerprint,
            binding=request.binding,
            deadline_at=request.context.context.deadline_at,
            deadline_remaining=timedelta(seconds=30),
            audit=request.context.context.audit,
        ),
        "第一句。",
        "第二句",
    )
    port.outcomes.append(expected)

    result = asyncio.run(GenerationKernel(port, clock=lambda: NOW).generate(request))

    assert result.mode is GenerationMode.GENERATED
    assert result.degradation_reason is GenerationDegradationReason.NONE
    assert result.generated_text == "第一句。第二句"
    assert result.text is not None
    assert result.text.validation_status == "UNVALIDATED"
    assert result.binding == request.binding
    provider_request = port.requests[0]
    assert provider_request.prompt == request.prompt
    assert provider_request.message_execution_id == "msg-exec-1"
    assert provider_request.prompt_fingerprint == request.prompt.prompt_fingerprint
    assert provider_request.deadline_remaining == timedelta(seconds=2)
    assert expected.segments == expected.chunks
    assert provider_request.model_dump().keys() == {
        "prompt",
        "message_execution_id",
        "prompt_fingerprint",
        "binding",
        "deadline_at",
        "deadline_remaining",
        "audit",
    }
    assert "access_context_hash" not in provider_request.model_dump_json()
    assert GeneratedValidationStatus.UNVALIDATED.value == "UNVALIDATED"
    assert result.model_validate(result.model_dump()) == result


def test_empty_evidence_is_refusal_without_provider_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = generation_request(context_factory, empty=True)
    port = ScriptedGenerator([])

    result = asyncio.run(GenerationKernel(port, clock=lambda: NOW).generate(request))

    assert request.prompt.mode is PromptMode.REFUSAL
    assert result.mode is GenerationMode.REFUSAL
    assert result.degradation_reason is GenerationDegradationReason.NO_EVIDENCE
    assert result.generated_text is None
    assert port.requests == []


def test_generation_result_empty_mode_keeps_provider_contract() -> None:
    result = GenerationResult(
        schema_version="1.0",
        message_execution_id="message-1",
        prompt_fingerprint="1" * 64,
        mode=GenerationMode.EMPTY,
        degradation_reason=GenerationDegradationReason.NONE,
        binding=binding(),
        text=None,
        finish_reason=GenerationFinishReason.STOP,
        usage=GeneratorUsage(input_tokens=0, output_tokens=0, total_tokens=0),
    )
    assert result.generated_text is None


@pytest.mark.parametrize(
    ("primary_outcome", "fallback_outcome", "mode", "reason"),
    [
        (
            RuntimeError("primary down"),
            None,
            GenerationMode.EVIDENCE_ONLY,
            GenerationDegradationReason.GENERATOR_UNAVAILABLE,
        ),
        (
            RuntimeError("primary down"),
            RuntimeError("fallback down"),
            GenerationMode.EVIDENCE_ONLY,
            GenerationDegradationReason.FALLBACK_UNAVAILABLE,
        ),
    ],
)
def test_provider_unavailability_degrades_to_evidence_only(
    context_factory: Callable[..., ProjectExecutionContext],
    primary_outcome: Exception,
    fallback_outcome: Exception | None,
    mode: GenerationMode,
    reason: GenerationDegradationReason,
) -> None:
    fallback = None if fallback_outcome is None else binding("generator-fallback-1")
    request = generation_request(context_factory, fallback_binding=fallback)
    primary = ScriptedGenerator([primary_outcome])
    fallback_port = ScriptedGenerator([] if fallback_outcome is None else [fallback_outcome])

    result = asyncio.run(
        GenerationKernel(
            primary,
            fallback_port=fallback_port,
            clock=lambda: NOW,
        ).generate(request)
    )

    assert result.mode is mode
    assert result.degradation_reason is reason
    assert result.generated_text is None
    assert len(primary.requests) == 1
    assert len(fallback_port.requests) == (0 if fallback is None else 1)


@pytest.mark.parametrize("error", [asyncio.CancelledError(), ExecutionDeadlineExceeded()])
def test_fallback_cancellation_and_deadline_are_not_converted(
    context_factory: Callable[..., ProjectExecutionContext],
    error: BaseException,
) -> None:
    request = generation_request(
        context_factory,
        fallback_binding=binding("generator-fallback-1"),
    )
    primary = ScriptedGenerator([RuntimeError("primary down")])

    class RaisingFallback:
        async def generate(self, _request: GeneratorRequest) -> GeneratorResult:
            raise error

    with pytest.raises(type(error)):
        asyncio.run(
            GenerationKernel(primary, fallback_port=RaisingFallback(), clock=lambda: NOW).generate(
                request
            )
        )


def test_invalid_fallback_contract_degrades_without_leaking_text(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    fallback_binding = binding("generator-fallback-1")
    request = generation_request(context_factory, fallback_binding=fallback_binding)
    primary = ScriptedGenerator([RuntimeError("primary down")])
    fallback = ScriptedGenerator([])
    fallback_request = GeneratorRequest(
        prompt=request.prompt,
        message_execution_id=request.prompt.message_execution_id,
        prompt_fingerprint=request.prompt.prompt_fingerprint,
        binding=fallback_binding,
        deadline_at=request.context.context.deadline_at,
        deadline_remaining=timedelta(seconds=2),
        audit=request.context.context.audit,
    )
    invalid = provider_result(fallback_request, "备用非法响应。").model_dump()
    invalid["message_execution_id"] = "wrong-execution"
    fallback.outcomes.append(DumpingGeneratorResult(invalid))

    result = asyncio.run(
        GenerationKernel(primary, fallback_port=fallback, clock=lambda: NOW).generate(request)
    )

    assert result.mode is GenerationMode.EVIDENCE_ONLY
    assert result.degradation_reason is GenerationDegradationReason.FALLBACK_CONTRACT_REJECTED


def test_contract_failure_uses_one_fallback_and_preserves_primary_reason(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    fallback_binding = binding("generator-fallback-1")
    request = generation_request(context_factory, fallback_binding=fallback_binding)
    primary = ScriptedGenerator([])
    fallback_port = ScriptedGenerator([])
    primary_request = GeneratorRequest(
        prompt=request.prompt,
        message_execution_id=request.prompt.message_execution_id,
        prompt_fingerprint=request.prompt.prompt_fingerprint,
        binding=request.binding,
        deadline_at=request.context.context.deadline_at,
        deadline_remaining=timedelta(seconds=30),
        audit=request.context.context.audit,
    )
    invalid_values = provider_result(primary_request, "非法主模型响应。").model_dump()
    invalid_values["prompt_fingerprint"] = "9" * 64
    primary.outcomes.append(DumpingGeneratorResult(invalid_values))
    fallback_request = primary_request.model_copy(update={"binding": fallback_binding})
    fallback_port.outcomes.append(provider_result(fallback_request, "备用模型回答。"))

    result = asyncio.run(
        GenerationKernel(primary, fallback_port=fallback_port, clock=lambda: NOW).generate(request)
    )

    assert result.mode is GenerationMode.FALLBACK_GENERATED
    assert result.degradation_reason is GenerationDegradationReason.GENERATOR_CONTRACT_REJECTED
    assert result.generated_text == "备用模型回答。"
    assert fallback_port.requests[0].binding == fallback_binding


@pytest.mark.parametrize("invalid_kind", ["missing_dump", "binding", "execution", "fingerprint"])
def test_invalid_provider_contract_is_never_admitted(
    context_factory: Callable[..., ProjectExecutionContext],
    invalid_kind: str,
) -> None:
    request = generation_request(context_factory)
    port = ScriptedGenerator([])
    provider_request = GeneratorRequest(
        prompt=request.prompt,
        message_execution_id=request.prompt.message_execution_id,
        prompt_fingerprint=request.prompt.prompt_fingerprint,
        binding=request.binding,
        deadline_at=request.context.context.deadline_at,
        deadline_remaining=timedelta(seconds=30),
        audit=request.context.context.audit,
    )
    if invalid_kind == "missing_dump":
        port.outcomes.append(MissingDump())
    else:
        values = provider_result(provider_request, "回答。").model_dump()
        if invalid_kind == "binding":
            values["binding"] = binding("unexpected").model_dump()
        elif invalid_kind == "execution":
            values["message_execution_id"] = "other-execution"
        else:
            values["prompt_fingerprint"] = "8" * 64
        port.outcomes.append(DumpingGeneratorResult(values))

    result = asyncio.run(GenerationKernel(port, clock=lambda: NOW).generate(request))

    assert result.mode is GenerationMode.EVIDENCE_ONLY
    assert result.degradation_reason is GenerationDegradationReason.GENERATOR_CONTRACT_REJECTED


def test_primary_empty_output_is_explicitly_marked_empty(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = generation_request(context_factory)
    provider = ScriptedGenerator([])
    provider_request = GeneratorRequest(
        prompt=request.prompt,
        message_execution_id=request.prompt.message_execution_id,
        prompt_fingerprint=request.prompt.prompt_fingerprint,
        binding=request.binding,
        deadline_at=request.context.context.deadline_at,
        deadline_remaining=timedelta(seconds=30),
        audit=request.context.context.audit,
    )
    provider.outcomes.append(provider_result(provider_request))

    result = asyncio.run(GenerationKernel(provider, clock=lambda: NOW).generate(request))

    assert result.mode is GenerationMode.EMPTY
    assert result.degradation_reason is GenerationDegradationReason.NONE
    assert result.text is None
    assert result.binding == request.binding


@pytest.mark.parametrize(
    "error",
    [asyncio.CancelledError(), ExecutionDeadlineExceeded()],
)
def test_cancellation_and_deadline_are_not_converted_to_degradation(
    context_factory: Callable[..., ProjectExecutionContext],
    error: BaseException,
) -> None:
    request = generation_request(context_factory)

    class RaisingGenerator:
        async def generate(self, _request: GeneratorRequest) -> GeneratorResult:
            raise error

    with pytest.raises(type(error)):
        asyncio.run(GenerationKernel(RaisingGenerator(), clock=lambda: NOW).generate(request))


def test_scope_and_input_rejections_happen_before_provider_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = generation_request(context_factory)
    provider = ScriptedGenerator([])
    invalid_context = cleared_context(
        lambda **_overrides: context_factory(project_id="other-project")
    )
    with pytest.raises(GenerationScopeRejected):
        asyncio.run(
            GenerationKernel(provider, clock=lambda: NOW).generate(
                replace(request, context=invalid_context)
            )
        )
    with pytest.raises(GenerationInputRejected):
        asyncio.run(GenerationKernel(provider, clock=lambda: NOW).generate(cast(Any, object())))
    with pytest.raises(GenerationInputRejected):
        asyncio.run(
            GenerationKernel(provider, clock=lambda: NOW).generate(
                replace(request, context=cast(Any, object()))
            )
        )
    with pytest.raises(GenerationInputRejected):
        asyncio.run(
            GenerationKernel(provider, clock=lambda: NOW).generate(
                replace(request, prompt=cast(Any, object()))
            )
        )
    with pytest.raises(GenerationInputRejected):
        asyncio.run(
            GenerationKernel(provider, clock=lambda: NOW).generate(
                replace(request, fallback_binding=request.binding)
            )
        )
    assert provider.requests == []


def test_context_deadline_is_rechecked_before_provider_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = generation_request(context_factory)
    expired = request.context.context.model_copy(update={"deadline_at": NOW})
    guarded = ExecutionContextGuard(lambda: NOW - timedelta(seconds=1)).validate(
        request.context.context.model_copy(update={"deadline_at": NOW + timedelta(seconds=1)})
    )
    expired_context = RevocationClearedExecutionContext(
        guarded_context=guarded,
        revocation_scope=RevocationScope.from_context(guarded.context),
        revocation_snapshot_version=request.context.revocation_snapshot_version,
        revocation_checked_at=NOW - timedelta(seconds=1),
        revocation_valid_until=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(
            GenerationKernel(ScriptedGenerator([]), clock=lambda: NOW).generate(
                replace(
                    request,
                    context=replace(
                        request.context,
                        guarded_context=replace(
                            expired_context.guarded_context,
                            context=expired,
                        ),
                    ),
                )
            )
        )


def test_domain_contracts_reject_inconsistent_values() -> None:
    with pytest.raises(ValidationError):
        GeneratorUsage(input_tokens=1, output_tokens=2, total_tokens=1)
    with pytest.raises(ValidationError):
        GeneratedTextChunk(sequence=1, text="bad\x00text")
    with pytest.raises(ValidationError):
        GeneratorResult(
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            binding=binding(),
            chunks=(GeneratedTextChunk(sequence=2, text="x"),),
            finish_reason=GenerationFinishReason.STOP,
            usage=GeneratorUsage(input_tokens=0, output_tokens=1, total_tokens=1),
        )
    with pytest.raises(ValidationError):
        GenerationResult(
            schema_version="1.0",
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            mode=GenerationMode.REFUSAL,
            degradation_reason=GenerationDegradationReason.NONE,
            binding=None,
            text=None,
            finish_reason=None,
            usage=None,
        )
    with pytest.raises(ValidationError):
        GeneratedText(chunks=())


def test_provider_result_limits_and_generated_text_limits() -> None:
    with pytest.raises(ValidationError):
        GeneratorResult(
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            binding=binding(),
            chunks=tuple(
                GeneratedTextChunk(sequence=sequence, text="x") for sequence in range(1, 1_026)
            ),
            finish_reason=GenerationFinishReason.STOP,
            usage=GeneratorUsage(input_tokens=0, output_tokens=1_025, total_tokens=1_025),
        )
    with pytest.raises(ValidationError):
        GeneratorResult(
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            binding=binding(),
            chunks=tuple(
                GeneratedTextChunk(sequence=sequence, text="x" * 131_072)
                for sequence in range(1, 17)
            ),
            finish_reason=GenerationFinishReason.STOP,
            usage=GeneratorUsage(input_tokens=0, output_tokens=2_097_152, total_tokens=2_097_152),
        )
    chunks = (
        GeneratedTextChunk(sequence=1, text="a"),
        GeneratedTextChunk(sequence=3, text="b"),
    )
    with pytest.raises(ValidationError):
        GeneratedText(chunks=chunks)
    with pytest.raises(ValidationError):
        GeneratedText(
            chunks=tuple(
                GeneratedTextChunk(sequence=sequence, text="x" * 131_072)
                for sequence in range(1, 17)
            )
        )


@pytest.mark.parametrize(
    "values",
    [
        {
            "mode": GenerationMode.GENERATED,
            "degradation_reason": GenerationDegradationReason.NONE,
            "binding": None,
            "text": None,
            "finish_reason": None,
            "usage": None,
        },
        {
            "mode": GenerationMode.EVIDENCE_ONLY,
            "degradation_reason": GenerationDegradationReason.GENERATOR_UNAVAILABLE,
            "binding": binding(),
            "text": None,
            "finish_reason": None,
            "usage": None,
        },
        {
            "mode": GenerationMode.GENERATED,
            "degradation_reason": GenerationDegradationReason.NONE,
            "binding": binding(),
            "text": None,
            "finish_reason": GenerationFinishReason.STOP,
            "usage": GeneratorUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        },
        {
            "mode": GenerationMode.GENERATED,
            "degradation_reason": GenerationDegradationReason.GENERATOR_UNAVAILABLE,
            "binding": binding(),
            "text": GeneratedText(chunks=(GeneratedTextChunk(sequence=1, text="x"),)),
            "finish_reason": GenerationFinishReason.STOP,
            "usage": GeneratorUsage(input_tokens=0, output_tokens=1, total_tokens=1),
        },
        {
            "mode": GenerationMode.FALLBACK_GENERATED,
            "degradation_reason": GenerationDegradationReason.FALLBACK_UNAVAILABLE,
            "binding": binding(),
            "text": GeneratedText(chunks=(GeneratedTextChunk(sequence=1, text="x"),)),
            "finish_reason": GenerationFinishReason.STOP,
            "usage": GeneratorUsage(input_tokens=0, output_tokens=1, total_tokens=1),
        },
        {
            "mode": GenerationMode.GENERATED,
            "degradation_reason": GenerationDegradationReason.NONE,
            "binding": None,
            "text": GeneratedText(chunks=(GeneratedTextChunk(sequence=1, text="x"),)),
            "finish_reason": None,
            "usage": None,
        },
        {
            "mode": GenerationMode.REFUSAL,
            "degradation_reason": GenerationDegradationReason.GENERATOR_UNAVAILABLE,
            "binding": None,
            "text": None,
            "finish_reason": None,
            "usage": None,
        },
        {
            "mode": GenerationMode.EVIDENCE_ONLY,
            "degradation_reason": GenerationDegradationReason.NONE,
            "binding": None,
            "text": None,
            "finish_reason": None,
            "usage": None,
        },
    ],
)
def test_generation_result_rejects_inconsistent_mode_contract(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GenerationResult(
            schema_version="1.0",
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            **cast(Any, values),
        )


@pytest.mark.parametrize(
    "values",
    [
        {
            "mode": GenerationMode.GENERATED,
            "degradation_reason": GenerationDegradationReason.GENERATOR_UNAVAILABLE,
            "binding": binding(),
            "text": GeneratedText(chunks=(GeneratedTextChunk(sequence=1, text="x"),)),
            "finish_reason": GenerationFinishReason.STOP,
            "usage": GeneratorUsage(input_tokens=0, output_tokens=1, total_tokens=1),
        },
        {
            "mode": GenerationMode.REFUSAL,
            "degradation_reason": GenerationDegradationReason.NO_EVIDENCE,
            "binding": None,
            "text": GeneratedText(chunks=(GeneratedTextChunk(sequence=1, text="x"),)),
            "finish_reason": None,
            "usage": None,
        },
    ],
)
def test_generation_result_rejects_primary_degradation_and_non_model_text(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        GenerationResult(
            schema_version="1.0",
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            **cast(Any, values),
        )


def test_claim_buffer_emits_complete_candidates_and_flushes_tail() -> None:
    buffer = ClaimBuffer(message_execution_id="message-1", prompt_fingerprint="1" * 64)
    assert buffer.pending_text == ""
    assert buffer.append(GeneratedTextChunk(sequence=1, text="第一句")) == ()
    claims = buffer.append(GeneratedTextChunk(sequence=2, text="。第二句\uff01尾部"))
    assert [(claim.sequence, claim.claim_id, claim.text) for claim in claims] == [
        (1, "claim-1", "第一句。"),
        (2, "claim-2", "第二句\uff01"),
    ]
    assert buffer.pending_text == "尾部"
    tail = buffer.flush()
    assert tail[0].text == "尾部"
    assert tail[0].validation_status == "UNVALIDATED"
    assert buffer.flush() == ()
    with pytest.raises(ClaimBufferClosed):
        buffer.append(GeneratedTextChunk(sequence=3, text="后续"))
    empty = ClaimBuffer(message_execution_id="message-1", prompt_fingerprint="1" * 64)
    assert empty.flush() == ()


@pytest.mark.parametrize(
    "operation",
    [
        "wrong_sequence",
        "not_chunk",
        "oversize",
    ],
)
def test_claim_buffer_rejects_invalid_or_unbounded_stream(
    operation: str,
) -> None:
    buffer = ClaimBuffer(message_execution_id="message-1", prompt_fingerprint="1" * 64)
    if operation == "wrong_sequence":
        with pytest.raises(ClaimBufferSequenceRejected):
            buffer.append(GeneratedTextChunk(sequence=2, text="x"))
    elif operation == "not_chunk":
        with pytest.raises(ClaimBufferSequenceRejected):
            buffer.append(cast(Any, object()))
    else:
        with pytest.raises(ClaimBufferRejected):
            for sequence in range(1, 17):
                buffer.append(GeneratedTextChunk(sequence=sequence, text="x" * 131_072))


def test_generated_text_and_claim_are_round_trip_strict() -> None:
    chunks = (
        GeneratedTextChunk(sequence=1, text="a"),
        GeneratedTextChunk(sequence=2, text="b"),
    )
    generated = GeneratedText(chunks=chunks)
    claim = CandidateClaim(
        message_execution_id="message-1",
        prompt_fingerprint="1" * 64,
        claim_id="claim-1",
        sequence=1,
        text="a",
    )
    assert generated.text == "ab"
    assert GeneratedText.model_validate(generated.model_dump()) == generated
    assert CandidateClaim.model_validate(claim.model_dump()) == claim


def test_request_contract_rechecks_prompt_identity_and_deadline(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = generation_request(context_factory)
    with pytest.raises(ValidationError):
        GeneratorRequest(
            prompt=request.prompt,
            message_execution_id="other-message",
            prompt_fingerprint=request.prompt.prompt_fingerprint,
            binding=request.binding,
            deadline_at=NOW,
            deadline_remaining=timedelta(seconds=1),
            audit=request.context.context.audit,
        )
    with pytest.raises(ValidationError):
        GeneratorRequest(
            prompt=request.prompt,
            message_execution_id=request.prompt.message_execution_id,
            prompt_fingerprint="2" * 64,
            binding=request.binding,
            deadline_at=NOW,
            deadline_remaining=timedelta(seconds=1),
            audit=request.context.context.audit,
        )
    with pytest.raises(ValidationError):
        GeneratorRequest(
            prompt=request.prompt,
            message_execution_id=request.prompt.message_execution_id,
            prompt_fingerprint=request.prompt.prompt_fingerprint,
            binding=request.binding,
            deadline_at=NOW.replace(tzinfo=None),
            deadline_remaining=timedelta(seconds=1),
            audit=request.context.context.audit,
        )
    with pytest.raises(ValidationError):
        GeneratorRequest(
            prompt=request.prompt,
            message_execution_id=request.prompt.message_execution_id,
            prompt_fingerprint=request.prompt.prompt_fingerprint,
            binding=request.binding,
            deadline_at=NOW,
            deadline_remaining=timedelta(0),
            audit=request.context.context.audit,
        )
