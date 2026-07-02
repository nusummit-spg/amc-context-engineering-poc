"""WS3 — Structured error responses."""
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, detail: dict | None = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ValidationFailedError(AppError):
    status_code = 422
    error_code = "validation_failed"


class UpstreamError(AppError):
    """Neo4j / Qdrant / LLM dependency failure."""
    status_code = 502
    error_code = "upstream_error"


class ContextQualityError(AppError):
    """Raised when assembled context fails the quality gate (WS5d)."""
    status_code = 422
    error_code = "context_quality_gate_failed"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
                "path": str(request.url.path),
            }
        },
    )
