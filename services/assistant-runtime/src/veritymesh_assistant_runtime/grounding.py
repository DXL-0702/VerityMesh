"""Provider-neutral Claim/Evidence grounding contracts and validation kernel."""

from __future__ import annotations

import asyncio
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from .evidence import Evidence, EvidencePacket, EvidencePacketStatus
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
from .generation import CandidateClaim
from .prompt_builder import Prompt, PromptMode
from .retrieval import CitationUrl, ProjectionText, Sha256Digest
from .revocation import (
    RevocationClearedExecutionContext,
    revalidate_cleared_execution_context,
)

GroundingConfidence = Annotated[
    float,
    Field(ge=0, le=1, strict=True, allow_inf_nan=False),
]


class GroundingLabel(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class GroundingMode(StrEnum):
    VALIDATED = "VALIDATED"
    FALLBACK_VALIDATED = "FALLBACK_VALIDATED"
    REJECTED = "REJECTED"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    REFUSAL = "REFUSAL"


class GroundingDegradationReason(StrEnum):
    NONE = "NONE"
    GROUNDING_UNAVAILABLE = "GROUNDING_UNAVAILABLE"
    GROUNDING_CONTRACT_REJECTED = "GROUNDING_CONTRACT_REJECTED"
    FALLBACK_UNAVAILABLE = "FALLBACK_UNAVAILABLE"
    FALLBACK_CONTRACT_REJECTED = "FALLBACK_CONTRACT_REJECTED"
    NO_EVIDENCE = "NO_EVIDENCE"


class GroundingRejectionReason(StrEnum):
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFIDENCE_BELOW_THRESHOLD = "CONFIDENCE_BELOW_THRESHOLD"


class GroundingBinding(FrozenStrictModel):
    """Trusted logical and physical identity resolved by server policy."""

    logical_model: Literal["grounding-validator-primary"]
    provider: Identifier
    region: Identifier
    api_mode: Identifier
    model: Identifier
    revision: Identifier
    configuration_fingerprint: Sha256Digest


class GroundingPolicy(FrozenStrictModel):
    """Deterministic acceptance gate applied after Provider classification."""

    minimum_supported_confidence: GroundingConfidence = 0.8
    max_evidence_items: Annotated[int, Field(ge=1, le=10, strict=True)] = 10


class GroundingEvidence(FrozenStrictModel):
    """Safe Evidence projection sent to a grounding Provider."""

    evidence_id: Identifier
    rank: Annotated[int, Field(ge=1, le=10, strict=True)]
    project_id: Identifier
    project_version: Identifier
    knowledge_release_id: Identifier
    title: ProjectionText
    section: ProjectionText
    text: ProjectionText
    citation_url: CitationUrl
    effective_from: datetime | None
    effective_to: datetime | None

    @field_validator("effective_from", "effective_to")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("grounding evidence timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("grounding evidence effective window must be ordered")
        return self


class GroundingRequest(FrozenStrictModel):
    """Minimal Provider request with no internal authorization or storage fields."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    claim: CandidateClaim
    claim_fingerprint: Sha256Digest
    evidence_set_fingerprint: Sha256Digest
    evidence: tuple[GroundingEvidence, ...]
    binding: GroundingBinding
    deadline_at: datetime
    deadline_remaining: timedelta
    audit: AuditContext

    @field_validator("deadline_at")
    @classmethod
    def normalize_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("grounding deadline must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.message_execution_id != self.claim.message_execution_id:
            raise ValueError("grounding request execution ID must match the claim")
        if self.prompt_fingerprint != self.claim.prompt_fingerprint:
            raise ValueError("grounding request fingerprint must match the claim")
        if not self.evidence:
            raise ValueError("grounding request requires Evidence")
        if len(self.evidence) > 10:
            raise ValueError("grounding request cannot exceed ten Evidence items")
        if tuple(item.rank for item in self.evidence) != tuple(range(1, len(self.evidence) + 1)):
            raise ValueError("grounding Evidence ranks must be contiguous and start at one")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("grounding request cannot repeat an Evidence ID")
        if self.deadline_remaining <= timedelta(0):
            raise ValueError("grounding request deadline must remain positive")
        return self


class GroundingDecision(FrozenStrictModel):
    """Structured semantic judgment returned by a Provider adapter."""

    label: GroundingLabel
    confidence: GroundingConfidence
    evidence_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if len(self.evidence_ids) > 10:
            raise ValueError("grounding decision cannot cite more than ten Evidence items")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("grounding decision cannot repeat an Evidence ID")
        if self.label is not GroundingLabel.INSUFFICIENT_EVIDENCE and not self.evidence_ids:
            raise ValueError("grounding semantic decisions require Evidence IDs")
        return self


class GroundingProviderResult(FrozenStrictModel):
    """Provider response before the domain acceptance gate is applied."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    claim_id: Identifier
    claim_fingerprint: Sha256Digest
    evidence_set_fingerprint: Sha256Digest
    binding: GroundingBinding
    decision: GroundingDecision


class GroundingPort(Protocol):
    """Task-semantic port; Provider SDK and framework types stay behind adapters."""

    async def validate(self, request: GroundingRequest) -> GroundingProviderResult: ...


class ValidatedClaim(FrozenStrictModel):
    """Only accepted Claim form; this is the sole DTO allowed to carry answer text."""

    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    claim_id: Identifier
    sequence: Annotated[int, Field(ge=1, strict=True)]
    text: Annotated[str, Field(strict=True, min_length=1, max_length=2_000_000)]
    evidence_ids: tuple[Identifier, ...]
    label: Literal[GroundingLabel.SUPPORTED] = GroundingLabel.SUPPORTED
    confidence: GroundingConfidence
    validation_status: Literal["VALIDATED"] = "VALIDATED"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        _validate_text_controls(value)
        return value

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        if not self.evidence_ids:
            raise ValueError("validated Claim requires Evidence IDs")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("validated Claim cannot repeat an Evidence ID")
        return self


class GroundingValidationResult(FrozenStrictModel):
    """Domain outcome; rejected and degraded modes never carry raw Claim text."""

    schema_version: Literal["1.0"]
    message_execution_id: Identifier
    prompt_fingerprint: Sha256Digest
    claim_id: Identifier
    claim_sequence: Annotated[int, Field(ge=1, strict=True)]
    mode: GroundingMode
    degradation_reason: GroundingDegradationReason
    label: GroundingLabel | None
    confidence: GroundingConfidence | None
    evidence_ids: tuple[Identifier, ...]
    rejection_reason: GroundingRejectionReason | None
    binding: GroundingBinding | None
    validated_claim: ValidatedClaim | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if len(self.evidence_ids) > 10:
            raise ValueError("grounding result cannot carry more than ten Evidence IDs")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("grounding result cannot repeat an Evidence ID")

        validated = self.mode in (
            GroundingMode.VALIDATED,
            GroundingMode.FALLBACK_VALIDATED,
        )
        if validated:
            if (
                self.label is not GroundingLabel.SUPPORTED
                or self.confidence is None
                or not self.evidence_ids
                or self.rejection_reason is not None
                or self.binding is None
                or self.validated_claim is None
            ):
                raise ValueError("validated outcome requires supported Claim and Evidence")
            if self.validated_claim.message_execution_id != self.message_execution_id:
                raise ValueError("validated Claim execution ID does not match the result")
            if self.validated_claim.prompt_fingerprint != self.prompt_fingerprint:
                raise ValueError("validated Claim fingerprint does not match the result")
            if self.validated_claim.claim_id != self.claim_id:
                raise ValueError("validated Claim ID does not match the result")
            if self.validated_claim.sequence != self.claim_sequence:
                raise ValueError("validated Claim sequence does not match the result")
            if self.validated_claim.evidence_ids != self.evidence_ids:
                raise ValueError("validated Claim Evidence IDs do not match the result")
            if self.validated_claim.confidence != self.confidence:
                raise ValueError("validated Claim confidence does not match the result")
            if self.mode is GroundingMode.VALIDATED and (
                self.degradation_reason is not GroundingDegradationReason.NONE
            ):
                raise ValueError("primary validation cannot claim degradation")
            if self.mode is GroundingMode.FALLBACK_VALIDATED and (
                self.degradation_reason
                not in (
                    GroundingDegradationReason.GROUNDING_UNAVAILABLE,
                    GroundingDegradationReason.GROUNDING_CONTRACT_REJECTED,
                )
            ):
                raise ValueError("fallback validation must preserve the primary failure")
            return self

        if self.validated_claim is not None:
            raise ValueError("non-validated outcome cannot carry a validated Claim")

        if self.mode is GroundingMode.REJECTED:
            if (
                self.label is None
                or self.confidence is None
                or self.rejection_reason is None
                or self.binding is None
                or self.degradation_reason
                not in (
                    GroundingDegradationReason.NONE,
                    GroundingDegradationReason.GROUNDING_UNAVAILABLE,
                    GroundingDegradationReason.GROUNDING_CONTRACT_REJECTED,
                )
            ):
                raise ValueError("rejected outcome requires a semantic Provider judgment")
            expected_reason = {
                GroundingLabel.PARTIALLY_SUPPORTED: GroundingRejectionReason.PARTIALLY_SUPPORTED,
                GroundingLabel.CONTRADICTED: GroundingRejectionReason.CONTRADICTED,
                GroundingLabel.INSUFFICIENT_EVIDENCE: (
                    GroundingRejectionReason.INSUFFICIENT_EVIDENCE
                ),
                GroundingLabel.SUPPORTED: GroundingRejectionReason.CONFIDENCE_BELOW_THRESHOLD,
            }[self.label]
            if self.rejection_reason is not expected_reason:
                raise ValueError("rejected outcome reason does not match its semantic label")
        elif self.mode is GroundingMode.EVIDENCE_ONLY:
            if (
                self.label is not None
                or self.confidence is not None
                or self.rejection_reason is not None
                or self.binding is not None
                or not self.evidence_ids
                or self.degradation_reason
                in (GroundingDegradationReason.NONE, GroundingDegradationReason.NO_EVIDENCE)
            ):
                raise ValueError("Evidence-only outcome requires safe Evidence and degradation")
        elif self.mode is GroundingMode.REFUSAL and (
            self.label is not None
            or self.confidence is not None
            or self.rejection_reason is not None
            or self.binding is not None
            or self.evidence_ids
            or self.degradation_reason is not GroundingDegradationReason.NO_EVIDENCE
        ):
            raise ValueError("refusal outcome cannot carry Provider or Evidence state")
        return self


class GroundingRejected(RuntimeError):
    code = "grounding_rejected"


class GroundingInputRejected(GroundingRejected):
    code = "grounding_input_rejected"


class GroundingScopeRejected(GroundingRejected):
    code = "grounding_scope_rejected"


@dataclass(frozen=True, slots=True)
class GroundingValidationRequest:
    context: RevocationClearedExecutionContext
    prompt: Prompt
    claim: CandidateClaim
    evidence_packet: EvidencePacket
    binding: GroundingBinding
    fallback_binding: GroundingBinding | None = None
    policy: GroundingPolicy = field(default_factory=GroundingPolicy)


class GroundingKernel:
    """Validates one Candidate Claim against one scope-bound Evidence Packet."""

    def __init__(
        self,
        port: GroundingPort,
        *,
        fallback_port: GroundingPort | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._port = port
        self._fallback_port = fallback_port or port
        self._context_guard = ExecutionContextGuard(clock)

    async def validate(self, request: GroundingValidationRequest) -> GroundingValidationResult:
        current, validated = self._validate_request(request)
        prompt = validated.prompt
        packet = validated.evidence_packet
        claim = validated.claim
        if prompt.mode is PromptMode.REFUSAL or packet.status is EvidencePacketStatus.EMPTY:
            return _refusal_result(prompt, claim)

        try:
            provider_request = self._provider_request(current, validated, validated.binding)
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise GroundingScopeRejected from error
        try:
            async with asyncio.timeout(provider_request.deadline_remaining.total_seconds()):
                raw_result = await self._port.validate(provider_request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except TimeoutError:
            self._validate_context(validated.context)
            return await self._fallback_or_evidence_only(
                validated,
                primary_reason=GroundingDegradationReason.GROUNDING_UNAVAILABLE,
            )
        except Exception:
            self._validate_context(validated.context)
            return await self._fallback_or_evidence_only(
                validated,
                primary_reason=GroundingDegradationReason.GROUNDING_UNAVAILABLE,
            )

        self._validate_context(validated.context)
        try:
            result = GroundingProviderResult.model_validate(raw_result.model_dump())
            self._validate_provider_result(result, provider_request)
        except (AttributeError, TypeError, ValueError, ValidationError):
            self._validate_context(validated.context)
            return await self._fallback_or_evidence_only(
                validated,
                primary_reason=GroundingDegradationReason.GROUNDING_CONTRACT_REJECTED,
            )
        return _decision_result(
            claim,
            result,
            validated,
            mode=GroundingMode.VALIDATED,
            degradation_reason=GroundingDegradationReason.NONE,
        )

    def _provider_request(
        self,
        current: GuardedExecutionContext,
        request: GroundingValidationRequest,
        binding: GroundingBinding,
    ) -> GroundingRequest:
        evidence = tuple(_grounding_evidence(item) for item in request.evidence_packet.evidence)
        return GroundingRequest(
            schema_version="1.0",
            message_execution_id=request.claim.message_execution_id,
            prompt_fingerprint=request.prompt.prompt_fingerprint,
            claim=request.claim,
            claim_fingerprint=grounding_claim_fingerprint(request.claim),
            evidence_set_fingerprint=grounding_evidence_set_fingerprint(request.evidence_packet),
            evidence=evidence,
            binding=binding,
            deadline_at=current.context.deadline_at,
            deadline_remaining=current.deadline_remaining,
            audit=current.context.audit,
        )

    async def _fallback_or_evidence_only(
        self,
        request: GroundingValidationRequest,
        *,
        primary_reason: GroundingDegradationReason,
    ) -> GroundingValidationResult:
        if request.fallback_binding is None:
            return _evidence_only_result(
                request.prompt,
                request.claim,
                request.evidence_packet,
                reason=primary_reason,
            )
        current = self._validate_context(request.context)
        try:
            fallback_request = self._provider_request(current, request, request.fallback_binding)
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise GroundingScopeRejected from error
        try:
            async with asyncio.timeout(fallback_request.deadline_remaining.total_seconds()):
                raw_result = await self._fallback_port.validate(fallback_request)
        except asyncio.CancelledError:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except TimeoutError:
            self._validate_context(request.context)
            return _evidence_only_result(
                request.prompt,
                request.claim,
                request.evidence_packet,
                reason=GroundingDegradationReason.FALLBACK_UNAVAILABLE,
            )
        except Exception:
            self._validate_context(request.context)
            return _evidence_only_result(
                request.prompt,
                request.claim,
                request.evidence_packet,
                reason=GroundingDegradationReason.FALLBACK_UNAVAILABLE,
            )

        self._validate_context(request.context)
        try:
            result = GroundingProviderResult.model_validate(raw_result.model_dump())
            self._validate_provider_result(result, fallback_request)
        except (AttributeError, TypeError, ValueError, ValidationError):
            self._validate_context(request.context)
            return _evidence_only_result(
                request.prompt,
                request.claim,
                request.evidence_packet,
                reason=GroundingDegradationReason.FALLBACK_CONTRACT_REJECTED,
            )
        return _decision_result(
            request.claim,
            result,
            request,
            mode=GroundingMode.FALLBACK_VALIDATED,
            degradation_reason=primary_reason,
        )

    def _validate_request(
        self,
        request: GroundingValidationRequest,
    ) -> tuple[GuardedExecutionContext, GroundingValidationRequest]:
        if not isinstance(request, GroundingValidationRequest):
            raise GroundingInputRejected("grounding kernel requires a GroundingValidationRequest")
        if not isinstance(request.context, RevocationClearedExecutionContext):
            raise GroundingInputRejected("grounding requires a cleared execution context")
        current = self._validate_context(request.context)
        try:
            prompt = Prompt.model_validate(request.prompt.model_dump())
            claim = CandidateClaim.model_validate(request.claim.model_dump())
            packet = EvidencePacket.model_validate(request.evidence_packet.model_dump())
            binding = GroundingBinding.model_validate(request.binding.model_dump())
            fallback_binding = (
                None
                if request.fallback_binding is None
                else GroundingBinding.model_validate(request.fallback_binding.model_dump())
            )
            policy = GroundingPolicy.model_validate(request.policy.model_dump())
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise GroundingInputRejected from error
        if fallback_binding is not None and fallback_binding == binding:
            raise GroundingInputRejected("primary and fallback bindings must differ")

        context = request.context.context
        if (
            prompt.message_execution_id != context.message_execution_id
            or prompt.project_id != context.project_id
            or prompt.project_version != context.project_version
            or prompt.locale != context.locale
            or prompt.knowledge_release_id != context.knowledge_release_id
            or claim.message_execution_id != context.message_execution_id
            or claim.prompt_fingerprint != prompt.prompt_fingerprint
            or tuple(item.evidence_id for item in packet.evidence) != prompt.evidence_ids
        ):
            raise GroundingScopeRejected("grounding inputs do not share one execution scope")
        if (
            packet.message_execution_id != context.message_execution_id
            or packet.project_execution_binding_id != context.project_execution_binding_id
            or packet.project_id != context.project_id
            or packet.project_version != context.project_version
            or packet.locale != context.locale
            or packet.access_segment is not context.access_segment
            or packet.access_context_hash != context.access_context_hash
            or packet.knowledge_release_id != context.knowledge_release_id
            or packet.execution_revocation_snapshot_version
            != request.context.revocation_snapshot_version
            or packet.execution_revocation_valid_until != request.context.revocation_valid_until
            or packet.effective_at > current.checked_at
            or packet.execution_revocation_valid_until <= current.checked_at
            or (
                packet.content_revocation_valid_until is not None
                and packet.content_revocation_valid_until <= current.checked_at
            )
        ):
            raise GroundingScopeRejected("Evidence Packet is not current for the execution")
        if len(packet.evidence) > policy.max_evidence_items:
            raise GroundingScopeRejected("Evidence exceeds the grounding policy limit")
        return current, GroundingValidationRequest(
            context=request.context,
            prompt=prompt,
            claim=claim,
            evidence_packet=packet,
            binding=binding,
            fallback_binding=fallback_binding,
            policy=policy,
        )

    def _validate_context(
        self,
        context: RevocationClearedExecutionContext,
    ) -> GuardedExecutionContext:
        return revalidate_cleared_execution_context(context, self._context_guard)

    @staticmethod
    def _validate_provider_result(
        result: GroundingProviderResult,
        request: GroundingRequest,
    ) -> None:
        if (
            result.message_execution_id != request.message_execution_id
            or result.prompt_fingerprint != request.prompt_fingerprint
            or result.claim_id != request.claim.claim_id
            or result.claim_fingerprint != request.claim_fingerprint
            or result.evidence_set_fingerprint != request.evidence_set_fingerprint
            or result.binding != request.binding
        ):
            raise ValueError("grounding result does not match the trusted request")
        allowed = {item.evidence_id for item in request.evidence}
        if not set(result.decision.evidence_ids).issubset(allowed):
            raise ValueError("grounding result references an unknown Evidence ID")


def _decision_result(
    claim: CandidateClaim,
    provider_result: GroundingProviderResult,
    request: GroundingValidationRequest,
    *,
    mode: GroundingMode,
    degradation_reason: GroundingDegradationReason,
) -> GroundingValidationResult:
    decision = provider_result.decision
    evidence_ids = _ordered_evidence_ids(decision.evidence_ids, request.evidence_packet)
    if (
        decision.label is GroundingLabel.SUPPORTED
        and decision.confidence >= request.policy.minimum_supported_confidence
    ):
        validated_claim = ValidatedClaim(
            message_execution_id=claim.message_execution_id,
            prompt_fingerprint=claim.prompt_fingerprint,
            claim_id=claim.claim_id,
            sequence=claim.sequence,
            text=claim.text,
            evidence_ids=evidence_ids,
            confidence=decision.confidence,
        )
        return GroundingValidationResult(
            schema_version="1.0",
            message_execution_id=claim.message_execution_id,
            prompt_fingerprint=claim.prompt_fingerprint,
            claim_id=claim.claim_id,
            claim_sequence=claim.sequence,
            mode=mode,
            degradation_reason=degradation_reason,
            label=decision.label,
            confidence=decision.confidence,
            evidence_ids=evidence_ids,
            rejection_reason=None,
            binding=provider_result.binding,
            validated_claim=validated_claim,
        )

    rejection_reason = {
        GroundingLabel.PARTIALLY_SUPPORTED: GroundingRejectionReason.PARTIALLY_SUPPORTED,
        GroundingLabel.CONTRADICTED: GroundingRejectionReason.CONTRADICTED,
        GroundingLabel.INSUFFICIENT_EVIDENCE: GroundingRejectionReason.INSUFFICIENT_EVIDENCE,
        GroundingLabel.SUPPORTED: GroundingRejectionReason.CONFIDENCE_BELOW_THRESHOLD,
    }[decision.label]
    return GroundingValidationResult(
        schema_version="1.0",
        message_execution_id=claim.message_execution_id,
        prompt_fingerprint=claim.prompt_fingerprint,
        claim_id=claim.claim_id,
        claim_sequence=claim.sequence,
        mode=GroundingMode.REJECTED,
        degradation_reason=degradation_reason,
        label=decision.label,
        confidence=decision.confidence,
        evidence_ids=evidence_ids,
        rejection_reason=rejection_reason,
        binding=provider_result.binding,
        validated_claim=None,
    )


def _refusal_result(prompt: Prompt, claim: CandidateClaim) -> GroundingValidationResult:
    return GroundingValidationResult(
        schema_version="1.0",
        message_execution_id=prompt.message_execution_id,
        prompt_fingerprint=prompt.prompt_fingerprint,
        claim_id=claim.claim_id,
        claim_sequence=claim.sequence,
        mode=GroundingMode.REFUSAL,
        degradation_reason=GroundingDegradationReason.NO_EVIDENCE,
        label=None,
        confidence=None,
        evidence_ids=(),
        rejection_reason=None,
        binding=None,
        validated_claim=None,
    )


def _evidence_only_result(
    prompt: Prompt,
    claim: CandidateClaim,
    packet: EvidencePacket,
    *,
    reason: GroundingDegradationReason,
) -> GroundingValidationResult:
    return GroundingValidationResult(
        schema_version="1.0",
        message_execution_id=prompt.message_execution_id,
        prompt_fingerprint=prompt.prompt_fingerprint,
        claim_id=claim.claim_id,
        claim_sequence=claim.sequence,
        mode=GroundingMode.EVIDENCE_ONLY,
        degradation_reason=reason,
        label=None,
        confidence=None,
        evidence_ids=tuple(item.evidence_id for item in packet.evidence),
        rejection_reason=None,
        binding=None,
        validated_claim=None,
    )


def _grounding_evidence(evidence: Evidence) -> GroundingEvidence:
    return GroundingEvidence(
        evidence_id=evidence.evidence_id,
        rank=evidence.rank,
        project_id=evidence.citation.project_id,
        project_version=evidence.citation.project_version,
        knowledge_release_id=evidence.citation.knowledge_release_id,
        title=evidence.title,
        section=evidence.citation.section,
        text=evidence.chunk_text,
        citation_url=evidence.citation.citation_url,
        effective_from=evidence.citation.effective_from,
        effective_to=evidence.citation.effective_to,
    )


def _ordered_evidence_ids(
    evidence_ids: tuple[str, ...],
    packet: EvidencePacket,
) -> tuple[str, ...]:
    selected = set(evidence_ids)
    return tuple(item.evidence_id for item in packet.evidence if item.evidence_id in selected)


def grounding_claim_fingerprint(claim: CandidateClaim) -> str:
    return _hash_payload(
        {
            "message_execution_id": claim.message_execution_id,
            "prompt_fingerprint": claim.prompt_fingerprint,
            "claim_id": claim.claim_id,
            "sequence": claim.sequence,
            "text": claim.text,
            "validation_status": claim.validation_status,
        }
    )


def grounding_evidence_set_fingerprint(packet: EvidencePacket) -> str:
    return _hash_payload(
        [
            {
                "evidence_id": item.evidence_id,
                "content_hash": item.content_hash,
                "knowledge_revision_id": item.citation.knowledge_revision_id,
                "citation_url": item.citation.citation_url,
            }
            for item in packet.evidence
        ]
    )


def _hash_payload(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _validate_text_controls(value: str) -> None:
    for character in value:
        if unicodedata.category(character) == "Cc" and character not in "\t\n\r":
            raise ValueError("grounding text contains a control character")
