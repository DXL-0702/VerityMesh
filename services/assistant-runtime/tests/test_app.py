import asyncio
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from conftest import NOW
from fastapi import FastAPI
from starlette.types import Message, Receive, Scope, Send
from veritymesh_assistant_runtime.app import create_app
from veritymesh_assistant_runtime.execution_context import ProjectExecutionContext
from veritymesh_assistant_runtime.internal_auth import (
    INTERNAL_CALLER_ASGI_EXTENSION,
    ScopeInternalCallerAuthenticator,
)

Caller = dict[str, str]


def internal_caller(service_id: str = "platform-api") -> Caller:
    return {
        "service_id": service_id,
        "authentication_method": "mtls",
        "certificate_fingerprint_sha256": "b" * 64,
    }


def request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    caller: Caller | None = None,
    extensions: object | None = None,
) -> tuple[int, dict[str, Any]]:
    encoded_body = json.dumps(body).encode() if body is not None else b""
    headers = [(b"content-type", b"application/json")] if body is not None else []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    if extensions is not None:
        scope["extensions"] = extensions
    if caller is not None:
        scope["extensions"] = {INTERNAL_CALLER_ASGI_EXTENSION: caller}

    request_sent = False
    messages: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": encoded_body, "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    async def invoke(receive_call: Receive, send_call: Send) -> None:
        await app(scope, receive_call, send_call)

    asyncio.run(invoke(receive, send))

    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return int(start["status"]), json.loads(response_body)


def context_body(context: ProjectExecutionContext) -> dict[str, Any]:
    return context.model_dump(mode="json")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/health/live", {"status": "live"}),
        ("/health/ready", {"status": "ready"}),
    ],
)
def test_health_routes_do_not_claim_domain_readiness(path: str, expected: dict[str, str]) -> None:
    status, response = request(create_app(clock=lambda: NOW), "GET", path)

    assert status == 200
    assert response == expected


def test_internal_openapi_schema_is_not_publicly_exposed() -> None:
    status, response = request(create_app(clock=lambda: NOW), "GET", "/openapi.json")

    assert status == 404
    assert response == {"detail": "Not Found"}


@pytest.mark.parametrize(
    "extensions",
    [None, "untrusted", {INTERNAL_CALLER_ASGI_EXTENSION: "untrusted"}],
)
def test_internal_route_fails_closed_without_a_verified_caller(
    context_factory: Callable[..., ProjectExecutionContext],
    extensions: object | None,
) -> None:
    status, response = request(
        create_app(clock=lambda: NOW),
        "POST",
        "/internal/v1/execution-context/validate",
        body=context_body(context_factory()),
        extensions=extensions,
    )

    assert status == 401
    assert response == {
        "error": {
            "code": "internal_authentication_required",
            "message": "internal authentication required",
        }
    }


def test_unauthenticated_request_cannot_probe_the_context_schema() -> None:
    status, response = request(
        create_app(clock=lambda: NOW),
        "POST",
        "/internal/v1/execution-context/validate",
        body={},
    )

    assert status == 401
    assert response["error"]["code"] == "internal_authentication_required"


@pytest.mark.parametrize(
    "caller",
    [
        {"service_id": "platform-api", "authentication_method": "header"},
        internal_caller("another-service"),
    ],
)
def test_internal_route_rejects_invalid_or_unapproved_caller_identity(
    context_factory: Callable[..., ProjectExecutionContext],
    caller: Caller,
) -> None:
    status, _response = request(
        create_app(clock=lambda: NOW),
        "POST",
        "/internal/v1/execution-context/validate",
        body=context_body(context_factory()),
        caller=caller,
    )

    assert status == 401


def test_context_validation_accepts_an_authenticated_platform_request(
    context_factory: Callable[..., ProjectExecutionContext],
) -> None:
    context = context_factory()

    status, response = request(
        create_app(clock=lambda: NOW),
        "POST",
        "/internal/v1/execution-context/validate",
        body=context_body(context),
        caller=internal_caller(),
    )

    assert status == 200
    assert response == {
        "schema_version": "1.0",
        "caller_service_id": "platform-api",
        "message_execution_id": "msg-exec-1",
        "project_id": "project-1",
        "project_version": "1.0.0",
        "project_execution_binding_id": "binding-1",
        "knowledge_release_id": "release-1",
        "deadline_remaining_ms": 2000,
    }


@pytest.mark.parametrize(
    ("overrides", "status_code", "error_code"),
    [
        (
            {"issued_at": NOW + timedelta(seconds=1)},
            403,
            "execution_context_not_yet_valid",
        ),
        (
            {
                "issued_at": NOW - timedelta(minutes=2),
                "deadline_at": NOW - timedelta(seconds=2),
                "expires_at": NOW - timedelta(seconds=1),
            },
            403,
            "execution_context_expired",
        ),
        ({"deadline_at": NOW}, 408, "execution_deadline_exceeded"),
    ],
)
def test_context_validation_maps_temporal_failures_without_leaking_context(
    context_factory: Callable[..., ProjectExecutionContext],
    overrides: dict[str, object],
    status_code: int,
    error_code: str,
) -> None:
    status, response = request(
        create_app(clock=lambda: NOW),
        "POST",
        "/internal/v1/execution-context/validate",
        body=context_body(context_factory(**overrides)),
        caller=internal_caller(),
    )

    assert status == status_code
    assert response["error"]["code"] == error_code
    assert "project-1" not in json.dumps(response)


def test_scope_authenticator_requires_an_allowlist() -> None:
    with pytest.raises(ValueError, match="at least one internal caller"):
        ScopeInternalCallerAuthenticator(())
