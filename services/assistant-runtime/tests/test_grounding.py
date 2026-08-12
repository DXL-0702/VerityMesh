import asyncio
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, cast

import pytest
from conftest import NOW
from pydantic import ValidationError
from test_prompt_builder import build_request, packet_and_context
from veritymesh_assistant_runtime.evidence import EvidencePacket
from veritymesh_assistant_runtime.execution_context import (
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
)
from veritymesh_assistant_runtime.generation import CandidateClaim
from veritymesh_assistant_runtime.grounding import (
    GroundingBinding,
    GroundingDecision,
    GroundingDegradationReason,
    GroundingEvidence,
    GroundingInputRejected,
    GroundingKernel,
    GroundingLabel,
    GroundingMode,
    GroundingPolicy,
    GroundingProviderResult,
    GroundingRejectionReason,
    GroundingRequest,
    GroundingScopeRejected,
    GroundingValidationRequest,
    GroundingValidationResult,
    ValidatedClaim,
    grounding_claim_fingerprint,
    grounding_evidence_set_fingerprint,
)
from veritymesh_assistant_runtime.prompt_builder import PromptBuilder

CONFIGURATION_FINGERPRINT = "7" * 64


class ScriptedGrounding:
    def __init__(self, outcomes: list[GroundingProviderResult | Exception | object]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[GroundingRequest] = []

    async def validate(self, request: GroundingRequest) -> GroundingProviderResult:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return cast(GroundingProviderResult, outcome)


class DumpingGroundingResult:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def model_dump(self) -> dict[str, object]:
        return self.values


class MissingDump:
    pass


def binding(revision: str = "grounding-revision-1") -> GroundingBinding:
    return GroundingBinding(
        logical_model="grounding-validator-primary",
        provider="aliyun-bailian",
        region="cn-beijing",
        api_mode="native-json",
        model="qwen3.7-flash-2026-07-15",
        revision=revision,
        configuration_fingerprint=CONFIGURATION_FINGERPRINT,
    )


def grounding_request(
    context_factory: Callable[..., ProjectExecutionContext],
    *,
    empty: bool = False,
    fallback_binding: GroundingBinding | None = None,
    policy: GroundingPolicy | None = None,
) -> GroundingValidationRequest:
    packet, context = packet_and_context(context_factory, empty=empty)
    prompt_request = build_request(
        context_factory,
        empty=empty,
        context=context,
        evidence_packet=packet,
    )
    prompt = PromptBuilder(clock=lambda: NOW).build(prompt_request)
    claim = CandidateClaim(
        message_execution_id=prompt.message_execution_id,
        prompt_fingerprint=prompt.prompt_fingerprint,
        claim_id="claim-1",
        sequence=1,
        text="项目 API 支持错误重试。",
    )
    return GroundingValidationRequest(
        context=context,
        prompt=prompt,
        claim=claim,
        evidence_packet=packet,
        binding=binding(),
        fallback_binding=fallback_binding,
        policy=policy or GroundingPolicy(),
    )


def provider_result(
    request: GroundingRequest,
    label: GroundingLabel,
    confidence: float,
    *evidence_ids: str,
    binding_override: GroundingBinding | None = None,
) -> GroundingProviderResult:
    return GroundingProviderResult(
        schema_version="1.0",
        message_execution_id=request.message_execution_id,
        prompt_fingerprint=request.prompt_fingerprint,
        claim_id=request.claim.claim_id,
        claim_fingerprint=request.claim_fingerprint,
        evidence_set_fingerprint=request.evidence_set_fingerprint,
        binding=binding_override or request.binding,
        decision=GroundingDecision(
            label=label,
            confidence=confidence,
            evidence_ids=evidence_ids,
        ),
    )


def make_provider_result(
    request: GroundingValidationRequest,
    label: GroundingLabel = GroundingLabel.SUPPORTED,
    confidence: float = 0.95,
    *evidence_ids: str,
) -> GroundingProviderResult:
    provider_request = GroundingRequest(
        schema_version="1.0",
        message_execution_id=request.claim.message_execution_id,
        prompt_fingerprint=request.prompt.prompt_fingerprint,
        claim=request.claim,
        claim_fingerprint=grounding_claim_fingerprint(request.claim),
        evidence_set_fingerprint=grounding_evidence_set_fingerprint(request.evidence_packet),
        evidence=tuple(
            GroundingEvidence(
                evidence_id=item.evidence_id,
                rank=item.rank,
                project_id=item.citation.project_id,
                project_version=item.citation.project_version,
                knowledge_release_id=item.citation.knowledge_release_id,
                title=item.title,
                section=item.citation.section,
                text=item.chunk_text,
                citation_url=item.citation.citation_url,
                effective_from=item.citation.effective_from,
                effective_to=item.citation.effective_to,
            )
            for item in request.evidence_packet.evidence
        ),
        binding=request.binding,
        deadline_at=request.context.context.deadline_at,
        deadline_remaining=timedelta(seconds=2),
        audit=request.context.context.audit,
    )
    selected_ids = evidence_ids or tuple(item.evidence_id for item in provider_request.evidence[:1])
    return provider_result(provider_request, label, confidence, *selected_ids)


def validated_result_values(
    request: GroundingValidationRequest,
) -> dict[str, Any]:
    provider = ScriptedGrounding([make_provider_result(request)])
    return asyncio.run(GroundingKernel(provider, clock=lambda: NOW).validate(request)).model_dump()


def test_supported_claim_becomes_validated_with_safe_provider_input(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory)
    provider = ScriptedGrounding([])
    provider.outcomes.append(make_provider_result(request))

    result = asyncio.run(GroundingKernel(provider, clock=lambda: NOW).validate(request))

    assert result.mode is GroundingMode.VALIDATED
    assert result.degradation_reason is GroundingDegradationReason.NONE
    assert result.label is GroundingLabel.SUPPORTED
    assert result.validated_claim is not None
    assert result.validated_claim.validation_status == "VALIDATED"
    assert result.validated_claim.text == request.claim.text
    assert result.evidence_ids == (request.evidence_packet.evidence[0].evidence_id,)
    provider_request = provider.requests[0]
    assert provider_request.claim == request.claim
    assert provider_request.evidence[0].text == request.evidence_packet.evidence[0].chunk_text
    assert "access_context_hash" not in provider_request.model_dump_json()
    assert "source_locator" not in provider_request.model_dump_json()
    assert GroundingValidationResult.model_validate(result.model_dump()) == result


@pytest.mark.parametrize(
    ("label", "reason"),
    [
        (GroundingLabel.PARTIALLY_SUPPORTED, GroundingRejectionReason.PARTIALLY_SUPPORTED),
        (GroundingLabel.CONTRADICTED, GroundingRejectionReason.CONTRADICTED),
        (GroundingLabel.INSUFFICIENT_EVIDENCE, GroundingRejectionReason.INSUFFICIENT_EVIDENCE),
        (GroundingLabel.SUPPORTED, GroundingRejectionReason.CONFIDENCE_BELOW_THRESHOLD),
    ],
)
def test_non_supported_or_low_confidence_claim_is_rejected_without_raw_answer_text(
    context_factory: Callable[..., ProjectExecutionContext],
    label: GroundingLabel,
    reason: GroundingRejectionReason,
) -> None:
    request = grounding_request(context_factory)
    provider = ScriptedGrounding([])
    confidence = 0.5 if label is GroundingLabel.SUPPORTED else 0.95
    provider.outcomes.append(make_provider_result(request, label, confidence))

    result = asyncio.run(GroundingKernel(provider, clock=lambda: NOW).validate(request))

    assert result.mode is GroundingMode.REJECTED
    assert result.label is label
    assert result.rejection_reason is reason
    assert result.validated_claim is None
    assert request.claim.text not in result.model_dump_json()


def test_empty_evidence_refuses_without_calling_grounding_provider(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory, empty=True)
    provider = ScriptedGrounding([])

    result = asyncio.run(GroundingKernel(provider, clock=lambda: NOW).validate(request))

    assert result.mode is GroundingMode.REFUSAL
    assert result.degradation_reason is GroundingDegradationReason.NO_EVIDENCE
    assert provider.requests == []


@pytest.mark.parametrize(
    ("primary_error", "fallback_error", "expected_mode", "expected_reason"),
    [
        (
            RuntimeError("primary unavailable"),
            None,
            GroundingMode.EVIDENCE_ONLY,
            GroundingDegradationReason.GROUNDING_UNAVAILABLE,
        ),
        (
            RuntimeError("primary unavailable"),
            RuntimeError("fallback unavailable"),
            GroundingMode.EVIDENCE_ONLY,
            GroundingDegradationReason.FALLBACK_UNAVAILABLE,
        ),
    ],
)
def test_grounding_failure_degrades_to_evidence_only(
    context_factory: Callable[..., ProjectExecutionContext],
    primary_error: Exception,
    fallback_error: Exception | None,
    expected_mode: GroundingMode,
    expected_reason: GroundingDegradationReason,
) -> None:
    fallback_binding = None if fallback_error is None else binding("grounding-fallback-1")
    request = grounding_request(context_factory, fallback_binding=fallback_binding)
    primary = ScriptedGrounding([primary_error])
    fallback = ScriptedGrounding([] if fallback_error is None else [fallback_error])

    result = asyncio.run(
        GroundingKernel(primary, fallback_port=fallback, clock=lambda: NOW).validate(request)
    )

    assert result.mode is expected_mode
    assert result.degradation_reason is expected_reason
    assert result.evidence_ids == tuple(
        item.evidence_id for item in request.evidence_packet.evidence
    )
    assert result.validated_claim is None


def test_fallback_supported_claim_preserves_primary_failure(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    fallback_binding = binding("grounding-fallback-1")
    request = grounding_request(context_factory, fallback_binding=fallback_binding)
    primary = ScriptedGrounding([RuntimeError("primary unavailable")])
    fallback = ScriptedGrounding([])
    fallback_request = replace(request, binding=fallback_binding)
    fallback.outcomes.append(make_provider_result(fallback_request, GroundingLabel.SUPPORTED, 0.9))
    result = asyncio.run(
        GroundingKernel(primary, fallback_port=fallback, clock=lambda: NOW).validate(request)
    )

    assert result.mode is GroundingMode.FALLBACK_VALIDATED
    assert result.degradation_reason is GroundingDegradationReason.GROUNDING_UNAVAILABLE
    assert result.validated_claim is not None
    assert fallback.requests[0].binding == fallback_binding


def test_grounding_provider_timeouts_degrade_safely(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory, fallback_binding=binding("fallback"))

    class TimeoutPrimary:
        async def validate(self, _request: GroundingRequest) -> GroundingProviderResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout grounding provider unexpectedly returned")

    class TimeoutFallback:
        async def validate(self, _request: GroundingRequest) -> GroundingProviderResult:
            await asyncio.sleep(10)
            raise AssertionError("timeout fallback provider unexpectedly returned")

    result = asyncio.run(
        GroundingKernel(
            TimeoutPrimary(),
            fallback_port=TimeoutFallback(),
            clock=lambda: NOW,
        ).validate(request)
    )

    assert result.mode is GroundingMode.EVIDENCE_ONLY
    assert result.degradation_reason is GroundingDegradationReason.FALLBACK_UNAVAILABLE


def test_grounding_provider_request_construction_failure_is_scope_rejected(
    context_factory: Callable[..., ProjectExecutionContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = grounding_request(context_factory)

    def reject(*_args: Any, **_kwargs: Any) -> GroundingRequest:
        raise ValueError("invalid provider request")

    monkeypatch.setattr(GroundingKernel, "_provider_request", reject)

    with pytest.raises(GroundingScopeRejected):
        asyncio.run(GroundingKernel(ScriptedGrounding([]), clock=lambda: NOW).validate(request))


def test_grounding_fallback_request_construction_failure_is_scope_rejected(
    context_factory: Callable[..., ProjectExecutionContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = grounding_request(context_factory, fallback_binding=binding("fallback"))
    calls = 0

    def reject_after_primary(*_args: Any, **_kwargs: Any) -> GroundingRequest:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("invalid fallback request")
        return GroundingRequest(
            schema_version="1.0",
            message_execution_id=request.claim.message_execution_id,
            prompt_fingerprint=request.prompt.prompt_fingerprint,
            claim=request.claim,
            claim_fingerprint=grounding_claim_fingerprint(request.claim),
            evidence_set_fingerprint=grounding_evidence_set_fingerprint(request.evidence_packet),
            evidence=tuple(
                GroundingEvidence(
                    evidence_id=item.evidence_id,
                    rank=item.rank,
                    project_id=item.citation.project_id,
                    project_version=item.citation.project_version,
                    knowledge_release_id=item.citation.knowledge_release_id,
                    title=item.title,
                    section=item.citation.section,
                    text=item.chunk_text,
                    citation_url=item.citation.citation_url,
                    effective_from=item.citation.effective_from,
                    effective_to=item.citation.effective_to,
                )
                for item in request.evidence_packet.evidence
            ),
            binding=request.binding,
            deadline_at=request.context.context.deadline_at,
            deadline_remaining=timedelta(seconds=2),
            audit=request.context.context.audit,
        )

    monkeypatch.setattr(GroundingKernel, "_provider_request", reject_after_primary)

    with pytest.raises(GroundingScopeRejected):
        asyncio.run(
            GroundingKernel(
                ScriptedGrounding([RuntimeError("primary unavailable")]),
                fallback_port=ScriptedGrounding([]),
                clock=lambda: NOW,
            ).validate(request)
        )


@pytest.mark.parametrize("error", [asyncio.CancelledError(), ExecutionDeadlineExceeded()])
def test_cancellation_and_deadline_are_not_converted(
    context_factory: Callable[..., ProjectExecutionContext],
    error: BaseException,
) -> None:
    request = grounding_request(context_factory, fallback_binding=binding("fallback"))

    class RaisingPort:
        async def validate(self, _request: GroundingRequest) -> GroundingProviderResult:
            raise error

    with pytest.raises(type(error)):
        asyncio.run(GroundingKernel(RaisingPort(), clock=lambda: NOW).validate(request))


@pytest.mark.parametrize("error", [asyncio.CancelledError(), ExecutionDeadlineExceeded()])
def test_fallback_cancellation_and_deadline_are_not_converted(
    context_factory: Callable[..., ProjectExecutionContext],
    error: BaseException,
) -> None:
    request = grounding_request(context_factory, fallback_binding=binding("fallback"))
    primary = ScriptedGrounding([RuntimeError("primary unavailable")])

    class RaisingFallback:
        async def validate(self, _request: GroundingRequest) -> GroundingProviderResult:
            raise error

    with pytest.raises(type(error)):
        asyncio.run(
            GroundingKernel(primary, fallback_port=RaisingFallback(), clock=lambda: NOW).validate(
                request
            )
        )


def test_invalid_provider_contract_uses_fallback_or_evidence_only(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory, fallback_binding=binding("fallback"))
    primary = ScriptedGrounding([])
    invalid = make_provider_result(request).model_dump()
    invalid["claim_id"] = "other-claim"
    primary.outcomes.append(DumpingGroundingResult(invalid))
    fallback = ScriptedGrounding([MissingDump()])

    result = asyncio.run(
        GroundingKernel(primary, fallback_port=fallback, clock=lambda: NOW).validate(request)
    )

    assert result.mode is GroundingMode.EVIDENCE_ONLY
    assert result.degradation_reason is GroundingDegradationReason.FALLBACK_CONTRACT_REJECTED


def test_scope_or_input_mismatch_fails_before_provider_call(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory)
    provider = ScriptedGrounding([])
    mismatched_claim = request.claim.model_copy(update={"message_execution_id": "other-message"})
    with pytest.raises(GroundingScopeRejected):
        asyncio.run(
            GroundingKernel(provider, clock=lambda: NOW).validate(
                replace(request, claim=mismatched_claim)
            )
        )
    with pytest.raises(GroundingInputRejected):
        asyncio.run(GroundingKernel(provider, clock=lambda: NOW).validate(cast(Any, object())))
    with pytest.raises(GroundingInputRejected):
        asyncio.run(
            GroundingKernel(provider, clock=lambda: NOW).validate(
                replace(request, fallback_binding=request.binding)
            )
        )
    assert provider.requests == []


def test_grounding_input_rejects_stale_packet_and_wrong_prompt_claim(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory)
    stale_values = request.evidence_packet.model_dump()
    stale_values["effective_at"] = NOW - timedelta(seconds=1)
    stale_values["execution_revocation_valid_until"] = NOW
    stale_packet = EvidencePacket.model_validate(stale_values)
    with pytest.raises(GroundingScopeRejected):
        asyncio.run(
            GroundingKernel(ScriptedGrounding([]), clock=lambda: NOW).validate(
                replace(request, evidence_packet=stale_packet)
            )
        )
    wrong_claim = request.claim.model_copy(update={"prompt_fingerprint": "8" * 64})
    with pytest.raises(GroundingScopeRejected):
        asyncio.run(
            GroundingKernel(ScriptedGrounding([]), clock=lambda: NOW).validate(
                replace(request, claim=wrong_claim)
            )
        )


def test_result_contract_matrix_and_kernel_revalidation(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    request = grounding_request(context_factory)
    base = validated_result_values(request)

    for result_field, claim_field, value in (
        ("message_execution_id", "message_execution_id", "other-message"),
        ("prompt_fingerprint", "prompt_fingerprint", "8" * 64),
        ("claim_id", "claim_id", "other-claim"),
        ("claim_sequence", "sequence", 2),
        ("evidence_ids", "evidence_ids", ("evidence-2",)),
        ("confidence", "confidence", 0.81),
    ):
        values = deepcopy(base)
        if result_field == "claim_sequence":
            values["validated_claim"][claim_field] = value
        else:
            values["validated_claim"][claim_field] = value
            if result_field != claim_field:
                values[result_field] = value
        with pytest.raises(ValidationError):
            GroundingValidationResult(**cast(Any, values))

    for values in (
        {**deepcopy(base), "evidence_ids": tuple(f"evidence-{index}" for index in range(1, 12))},
        {**deepcopy(base), "evidence_ids": ("evidence-1", "evidence-1")},
    ):
        with pytest.raises(ValidationError):
            GroundingValidationResult(**cast(Any, values))

    invalid_validated = deepcopy(base)
    invalid_validated["validated_claim"] = None
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, invalid_validated))

    primary_degraded = deepcopy(base)
    primary_degraded["degradation_reason"] = GroundingDegradationReason.GROUNDING_UNAVAILABLE
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, primary_degraded))

    fallback_without_primary_reason = deepcopy(base)
    fallback_without_primary_reason["mode"] = GroundingMode.FALLBACK_VALIDATED
    fallback_without_primary_reason["degradation_reason"] = GroundingDegradationReason.NONE
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, fallback_without_primary_reason))

    non_validated_with_claim = deepcopy(base)
    non_validated_with_claim["mode"] = GroundingMode.EVIDENCE_ONLY
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, non_validated_with_claim))

    rejected_without_judgment = deepcopy(base)
    rejected_without_judgment.update(
        mode=GroundingMode.REJECTED,
        degradation_reason=GroundingDegradationReason.NONE,
        label=None,
        confidence=None,
        rejection_reason=None,
        binding=None,
        validated_claim=None,
    )
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, rejected_without_judgment))

    rejected_with_wrong_reason = deepcopy(base)
    rejected_with_wrong_reason.update(
        mode=GroundingMode.REJECTED,
        degradation_reason=GroundingDegradationReason.NONE,
        rejection_reason=GroundingRejectionReason.CONTRADICTED,
        validated_claim=None,
    )
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, rejected_with_wrong_reason))

    invalid_evidence_only = deepcopy(base)
    invalid_evidence_only.update(
        mode=GroundingMode.EVIDENCE_ONLY,
        degradation_reason=GroundingDegradationReason.GROUNDING_UNAVAILABLE,
        label=None,
        confidence=None,
        evidence_ids=(),
        rejection_reason=None,
        binding=None,
        validated_claim=None,
    )
    with pytest.raises(ValidationError):
        GroundingValidationResult(**cast(Any, invalid_evidence_only))

    request_with_invalid_context = replace(request, context=cast(Any, object()))
    with pytest.raises(GroundingInputRejected):
        asyncio.run(
            GroundingKernel(ScriptedGrounding([]), clock=lambda: NOW).validate(
                request_with_invalid_context
            )
        )

    request_with_invalid_prompt = replace(request, prompt=cast(Any, object()))
    with pytest.raises(GroundingInputRejected):
        asyncio.run(
            GroundingKernel(ScriptedGrounding([]), clock=lambda: NOW).validate(
                request_with_invalid_prompt
            )
        )

    with pytest.raises(GroundingScopeRejected):
        asyncio.run(
            GroundingKernel(ScriptedGrounding([]), clock=lambda: NOW).validate(
                replace(request, policy=GroundingPolicy(max_evidence_items=1))
            )
        )

    unknown_evidence_provider = ScriptedGrounding(
        [make_provider_result(request, GroundingLabel.SUPPORTED, 0.95, "unknown-evidence")]
    )
    unknown_result = asyncio.run(
        GroundingKernel(unknown_evidence_provider, clock=lambda: NOW).validate(request)
    )
    assert unknown_result.mode is GroundingMode.EVIDENCE_ONLY
    assert (
        unknown_result.degradation_reason is GroundingDegradationReason.GROUNDING_CONTRACT_REJECTED
    )


def test_provider_request_and_decision_contracts_fail_closed() -> None:
    claim = CandidateClaim(
        message_execution_id="message-1",
        prompt_fingerprint="1" * 64,
        claim_id="claim-1",
        sequence=1,
        text="事实。",
    )
    evidence = GroundingEvidence(
        evidence_id="evidence-1",
        rank=1,
        project_id="project-1",
        project_version="1.0.0",
        knowledge_release_id="release-1",
        title="标题",
        section="章节",
        text="正文",
        citation_url="/citations/1",
        effective_from=None,
        effective_to=None,
    )
    kwargs = {
        "schema_version": "1.0",
        "message_execution_id": "message-1",
        "prompt_fingerprint": "1" * 64,
        "claim": claim,
        "claim_fingerprint": "2" * 64,
        "evidence_set_fingerprint": "3" * 64,
        "evidence": (evidence,),
        "binding": binding(),
        "deadline_at": NOW,
        "deadline_remaining": timedelta(seconds=1),
        "audit": {"trace_id": "trace-1", "request_id": "request-1"},
    }
    with pytest.raises(ValidationError):
        GroundingRequest(**cast(Any, {**kwargs, "message_execution_id": "other"}))
    with pytest.raises(ValidationError):
        GroundingRequest(**cast(Any, {**kwargs, "prompt_fingerprint": "4" * 64}))
    with pytest.raises(ValidationError):
        GroundingRequest(**cast(Any, {**kwargs, "evidence": ()}))
    with pytest.raises(ValidationError):
        GroundingDecision(label=GroundingLabel.SUPPORTED, confidence=0.9)
    with pytest.raises(ValidationError):
        GroundingDecision(
            label=GroundingLabel.SUPPORTED,
            confidence=0.9,
            evidence_ids=("evidence-1", "evidence-1"),
        )
    with pytest.raises(ValidationError):
        GroundingEvidence(**{**evidence.model_dump(), "effective_from": NOW, "effective_to": NOW})
    with pytest.raises(ValidationError):
        ValidatedClaim(
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            claim_id="claim-1",
            sequence=1,
            text="bad\x00text",
            evidence_ids=("evidence-1",),
            confidence=0.9,
        )


def test_request_and_evidence_limits_fail_closed() -> None:
    evidence = GroundingEvidence(
        evidence_id="evidence-1",
        rank=1,
        project_id="project-1",
        project_version="1.0.0",
        knowledge_release_id="release-1",
        title="标题",
        section="章节",
        text="正文",
        citation_url="/citations/1",
        effective_from=None,
        effective_to=None,
    )
    claim = CandidateClaim(
        message_execution_id="message-1",
        prompt_fingerprint="1" * 64,
        claim_id="claim-1",
        sequence=1,
        text="事实。",
    )
    common: dict[str, Any] = {
        "schema_version": "1.0",
        "message_execution_id": "message-1",
        "prompt_fingerprint": "1" * 64,
        "claim": claim,
        "claim_fingerprint": "2" * 64,
        "evidence_set_fingerprint": "3" * 64,
        "binding": binding(),
        "deadline_at": NOW,
        "deadline_remaining": timedelta(seconds=1),
        "audit": {"trace_id": "trace-1", "request_id": "request-1"},
    }
    with pytest.raises(ValidationError):
        GroundingEvidence.model_validate(
            {**evidence.model_dump(), "effective_from": datetime(2026, 1, 1)}
        )
    with pytest.raises(ValidationError):
        GroundingRequest(
            **cast(Any, {**common, "deadline_at": datetime(2026, 1, 1), "evidence": (evidence,)})
        )
    with pytest.raises(ValidationError):
        GroundingRequest(
            **cast(
                Any,
                {
                    **common,
                    "evidence": tuple(
                        evidence.model_copy(update={"evidence_id": f"evidence-{index}"})
                        for index in range(1, 12)
                    ),
                },
            )
        )
    with pytest.raises(ValidationError):
        GroundingRequest(
            **cast(
                Any,
                {
                    **common,
                    "evidence": (
                        evidence,
                        evidence.model_copy(update={"evidence_id": "evidence-2", "rank": 3}),
                    ),
                },
            )
        )
    with pytest.raises(ValidationError):
        GroundingRequest(
            **cast(
                Any,
                {
                    **common,
                    "evidence": (
                        evidence,
                        evidence.model_copy(update={"rank": 2}),
                    ),
                },
            )
        )
    with pytest.raises(ValidationError):
        GroundingRequest(
            **cast(Any, {**common, "evidence": (evidence,), "deadline_remaining": timedelta(0)})
        )

    ten_ids = tuple(f"evidence-{index}" for index in range(1, 12))
    with pytest.raises(ValidationError):
        GroundingDecision(
            label=GroundingLabel.SUPPORTED,
            confidence=0.9,
            evidence_ids=ten_ids,
        )
    with pytest.raises(ValidationError):
        ValidatedClaim(
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            claim_id="claim-1",
            sequence=1,
            text="事实。",
            evidence_ids=(),
            confidence=0.9,
        )
    with pytest.raises(ValidationError):
        ValidatedClaim(
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            claim_id="claim-1",
            sequence=1,
            text="事实。",
            evidence_ids=("evidence-1", "evidence-1"),
            confidence=0.9,
        )


def test_result_modes_and_fingerprints_are_strict() -> None:
    with pytest.raises(ValidationError):
        GroundingValidationResult(
            schema_version="1.0",
            message_execution_id="message-1",
            prompt_fingerprint="1" * 64,
            claim_id="claim-1",
            claim_sequence=1,
            mode=GroundingMode.REFUSAL,
            degradation_reason=GroundingDegradationReason.GROUNDING_UNAVAILABLE,
            label=None,
            confidence=None,
            evidence_ids=(),
            rejection_reason=None,
            binding=None,
            validated_claim=None,
        )
    assert (
        grounding_claim_fingerprint(
            CandidateClaim(
                message_execution_id="message-1",
                prompt_fingerprint="1" * 64,
                claim_id="claim-1",
                sequence=1,
                text="事实。",
            )
        )
        != ""
    )
