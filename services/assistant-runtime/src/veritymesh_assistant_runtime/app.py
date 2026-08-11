"""FastAPI entry point for the constrained assistant runtime."""

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .execution_context import (
    Clock,
    ExecutionContextGuard,
    ExecutionContextRejected,
    ExecutionDeadlineExceeded,
    ProjectExecutionContext,
    utc_now,
)
from .internal_auth import (
    InternalAuthenticationError,
    InternalCaller,
    InternalCallerAuthenticator,
    ScopeInternalCallerAuthenticator,
)


class ExecutionContextValidationResponse(BaseModel):
    """Minimal acknowledgement that does not expose authorization internals."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str
    caller_service_id: str
    message_execution_id: str
    project_id: str
    project_version: str
    project_execution_binding_id: str
    knowledge_release_id: str
    deadline_remaining_ms: int


def create_app(
    *,
    clock: Clock = utc_now,
    caller_authenticator: InternalCallerAuthenticator | None = None,
) -> FastAPI:
    """Build an application whose internal routes fail closed by default."""

    app = FastAPI(
        title="VerityMesh Assistant Runtime",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    guard = ExecutionContextGuard(clock)
    authenticator = caller_authenticator or ScopeInternalCallerAuthenticator()

    async def require_internal_caller(request: Request) -> InternalCaller:
        return await authenticator.authenticate(request)

    @app.exception_handler(InternalAuthenticationError)
    async def handle_internal_authentication_error(
        _request: Request,
        error: InternalAuthenticationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": error.code, "message": "internal authentication required"}},
        )

    @app.exception_handler(ExecutionContextRejected)
    async def handle_execution_context_rejected(
        _request: Request,
        error: ExecutionContextRejected,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": error.code, "message": "execution context rejected"}},
        )

    @app.exception_handler(ExecutionDeadlineExceeded)
    async def handle_execution_deadline_exceeded(
        _request: Request,
        error: ExecutionDeadlineExceeded,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=408,
            content={"error": {"code": error.code, "message": "execution deadline exceeded"}},
        )

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/internal/v1/execution-context/validate",
        response_model=ExecutionContextValidationResponse,
    )
    async def validate_execution_context(
        context: ProjectExecutionContext,
        caller: Annotated[InternalCaller, Depends(require_internal_caller)],
    ) -> ExecutionContextValidationResponse:
        guarded = guard.validate(context)
        return ExecutionContextValidationResponse(
            schema_version=context.schema_version,
            caller_service_id=caller.service_id,
            message_execution_id=context.message_execution_id,
            project_id=context.project_id,
            project_version=context.project_version,
            project_execution_binding_id=context.project_execution_binding_id,
            knowledge_release_id=context.knowledge_release_id,
            deadline_remaining_ms=guarded.deadline_remaining_ms,
        )

    return app


app = create_app()
