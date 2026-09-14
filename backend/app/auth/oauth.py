"""OAuth adapter interface and the stubbed provider wiring.

Per the task brief, OAuth token exchange is **stubbed** here behind a
clearly-marked adapter so we can wire real Google/GitHub HTTP calls in
later. The shape is:

* :class:`OAuthProvider` — what a real adapter would look like
* :class:`StubOAuthProvider` — what we ship in MVP; rejects with a
  clear "not implemented" message at the callback boundary so it's
  obvious to anyone touching this code that the swap point is here.

The session token itself (the piece issued *after* a successful OAuth
exchange) is real — it's just an HMAC-signed JWT carrying ``user_id``,
``expires_at``. That part doesn't change when the real adapter lands.
"""

from __future__ import annotations

import abc
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings
from app.core.errors import bad_request

Provider = Literal["google", "github"]


@dataclass(frozen=True)
class OAuthUserInfo:
    """What the real adapter returns after a successful token exchange."""

    provider: Provider
    provider_user_id: str
    email: str | None
    display_name: str | None


class OAuthProvider(abc.ABC):
    """Adapter interface. Wire a real one in here when ready."""

    name: Provider

    @abc.abstractmethod
    async def exchange(self, *, code: str, redirect_uri: str, state: str) -> OAuthUserInfo: ...

    @abc.abstractmethod
    async def build_authorize_url(self, *, state: str, redirect_uri: str) -> str: ...


class StubOAuthProvider(OAuthProvider):
    """Stub: clearly-marked adapter boundary.

    Calling ``exchange`` raises a ``bad_request`` whose ``code`` is
    ``oauth_not_implemented`` — that's the seam where the real Google /
    GitHub HTTP exchange would land. Calling ``build_authorize_url``
    returns ``about:blank`` so the redirect step at least completes in
    dev without crashing, but no token exchange happens.
    """

    def __init__(self, name: Provider) -> None:
        self.name = name

    async def exchange(self, *, code: str, redirect_uri: str, state: str) -> OAuthUserInfo:
        # The OAuth provider's HTTP token-exchange call would live here.
        # In production this hits Google's token endpoint (or GitHub's),
        # then the userinfo endpoint, and returns an OAuthUserInfo.
        # For MVP we refuse explicitly so the boundary is visible.
        raise bad_request(
            "oauth_not_implemented",
            f"OAuth exchange for provider={self.name} is a stub. "
            "Implement app.auth.oauth.<Google|GitHub>Provider before going live.",
            details={"provider": self.name, "hint": "see app/auth/oauth.py"},
        )

    async def build_authorize_url(self, *, state: str, redirect_uri: str) -> str:
        # Real implementation: redirect to the provider's authorize endpoint.
        # For MVP, return a sentinel so the redirect doesn't crash dev.
        return f"about:blank#{self.name}:{state}"


# --- Session token (HMAC JWT-like) -------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def issue_session_token(user_id: str, *, ttl_seconds: int | None = None) -> str:
    """Issue an HMAC-signed token carrying ``user_id`` and expiry."""

    ttl = ttl_seconds if ttl_seconds is not None else settings.oauth_session_ttl_seconds
    header = {"alg": "HS256", "typ": "APACK"}
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + ttl,
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(settings.oauth_jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(sig)}"


def verify_session_token(token: str) -> dict:
    """Return the verified payload or raise :class:`bad_request`."""

    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise bad_request("invalid_token", "Malformed session token.") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(
        settings.oauth_jwt_secret.encode(), signing_input, hashlib.sha256
    ).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception as exc:  # pragma: no cover - defensive
        raise bad_request("invalid_token", "Malformed session token signature.") from exc
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise bad_request("invalid_token", "Session token signature mismatch.")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise bad_request("invalid_token", "Malformed session token payload.") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise bad_request("token_expired", "Session token has expired.")
    return payload


def get_provider(name: str) -> OAuthProvider:
    """Return the adapter for ``name``. All MVP providers are stubs."""

    if name not in ("google", "github"):
        raise bad_request("unsupported_provider", f"Provider {name!r} is not supported.")
    return StubOAuthProvider(name)  # type: ignore[arg-type]


__all__ = [
    "OAuthProvider",
    "StubOAuthProvider",
    "OAuthUserInfo",
    "Provider",
    "issue_session_token",
    "verify_session_token",
    "get_provider",
]
