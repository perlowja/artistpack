"""Standard error envelope per ``docs/api-design.md``.

The doc mandates:

    {"error": {"code": "...", "message": "...", "details": {...}}}

with the HTTP status matching the error class (400 validation, 401/403
auth, 404 not found, 409 conflict, 422 semantic validation — schema-valid
but fails a publish-policy gate). We also map it to FastAPI's
``HTTPException`` so that ``RequestValidationError`` flows through the
same shape without per-endpoint boilerplate.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(HTTPException):
    """An HTTP error whose body conforms to the envelope shape.

    Use this anywhere we want to return a structured error. ``details``
    is the optional per-error payload (e.g. a list of validation
    issues, or the count of conflicting rows). It serializes to JSON
    via FastAPI's standard handler.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        body: dict[str, Any] = {"error": {"code": code, "message": message, "details": details}}
        super().__init__(status_code=status_code, detail=body, headers=headers)


# --- Specific error factories for the doc-mandated status classes -------------

def bad_request(code: str, message: str, details: Any | None = None) -> APIError:
    return APIError(
        code=code, message=message, status_code=status.HTTP_400_BAD_REQUEST, details=details
    )


def unauthorized(code: str = "unauthorized", message: str = "Authentication required.") -> APIError:
    return APIError(code=code, message=message, status_code=status.HTTP_401_UNAUTHORIZED)


def forbidden(code: str = "forbidden", message: str = "You do not have permission for this action.", details: Any | None = None) -> APIError:
    return APIError(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN, details=details)


def not_found(code: str = "not_found", message: str = "Resource not found.") -> APIError:
    return APIError(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


def conflict(code: str, message: str, details: Any | None = None) -> APIError:
    return APIError(code=code, message=message, status_code=status.HTTP_409_CONFLICT, details=details)


def unprocessable(code: str, message: str, details: Any | None = None) -> APIError:
    """422 semantic validation — passes the JSON Schema check but fails a policy gate."""

    # Starlette renamed ``HTTP_422_UNPROCESSABLE_ENTITY`` to
    # ``HTTP_422_UNPROCESSABLE_CONTENT``; keep both so we work on the
    # installed Starlette version (and silence the DeprecationWarning).
    status_code = getattr(
        status, "HTTP_422_UNPROCESSABLE_CONTENT", status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return APIError(
        code=code, message=message, status_code=status_code, details=details
    )


# --- Handlers so existing FastAPI exceptions also conform to the envelope ------

def _envelope_response(status_code: int, code: str, message: str, details: Any | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else None
    if detail is None or "error" not in detail:
        return _envelope_response(exc.status_code, "error", str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=detail)


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Re-shape plain HTTPException into the envelope; the message comes from
    # the exception's `detail` (string or already-shaped dict).
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return _envelope_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail))


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    status_code = getattr(
        status, "HTTP_422_UNPROCESSABLE_CONTENT", status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return _envelope_response(
        status_code,
        "request_validation_error",
        "Request payload failed validation.",
        details={"errors": exc.errors()},
    )
