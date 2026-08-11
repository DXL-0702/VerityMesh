"""Authenticated internal-caller boundary for the assistant runtime."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Annotated, Literal, Protocol

from fastapi import Request
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

INTERNAL_CALLER_ASGI_EXTENSION = "veritymesh.internal-caller"

ServiceIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:\-]*$",
    ),
]
CertificateFingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class InternalCaller(BaseModel):
    """Identity emitted only after the transport has verified client mTLS."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    service_id: ServiceIdentifier
    authentication_method: Literal["mtls"]
    certificate_fingerprint_sha256: CertificateFingerprint


class InternalAuthenticationError(RuntimeError):
    code = "internal_authentication_required"


class InternalCallerAuthenticator(Protocol):
    async def authenticate(self, request: Request) -> InternalCaller: ...


class ScopeInternalCallerAuthenticator:
    """Consumes a server-controlled ASGI extension, never an HTTP identity header."""

    def __init__(self, allowed_service_ids: Collection[str] = ("platform-api",)) -> None:
        self._allowed_service_ids = frozenset(allowed_service_ids)
        if not self._allowed_service_ids:
            raise ValueError("at least one internal caller must be allowed")

    async def authenticate(self, request: Request) -> InternalCaller:
        extensions = request.scope.get("extensions")
        if not isinstance(extensions, Mapping):
            raise InternalAuthenticationError

        raw_caller = extensions.get(INTERNAL_CALLER_ASGI_EXTENSION)
        if not isinstance(raw_caller, Mapping):
            raise InternalAuthenticationError

        try:
            caller = InternalCaller.model_validate(raw_caller, strict=True)
        except ValidationError as error:
            raise InternalAuthenticationError from error

        if caller.service_id not in self._allowed_service_ids:
            raise InternalAuthenticationError
        return caller
