"""Common API schemas (pagination, error envelope responses, etc.)."""

from __future__ import annotations

import base64
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Cursor-paginated response envelope.

    Per ``docs/api-design.md`` §Conventions: every list endpoint returns
    ``{"items": [...], "next_cursor": "..."|null}``. The cursor itself
    is an opaque, base64url-encoded JSON blob; clients should treat it
    as a black box and not parse it.
    """

    items: list[T]
    next_cursor: str | None = None


def encode_cursor(payload: dict[str, Any]) -> str:
    """Encode a paging cursor (opaque to the client)."""

    raw = _canonical_json(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a paging cursor. Raises ``ValueError`` on malformed input."""

    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding)
    import json as _json

    return _json.loads(raw.decode("utf-8"))


def _canonical_json(obj: Any) -> str:
    import json as _json

    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody = Field(...)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "artistpack-backend"
    version: str = "0.1.0"


__all__ = [
    "Page",
    "encode_cursor",
    "decode_cursor",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthResponse",
]
