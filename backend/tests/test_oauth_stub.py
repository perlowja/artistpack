"""End-to-end tests for the OAuth callback stub.

The OAuth provider HTTP exchange is intentionally **not implemented**
in this Task 7 build — see ``app/auth/oauth.py``. The
``POST /api/v1/auth/oauth/{provider}/callback`` endpoint must therefore
surface a clear ``oauth_not_implemented`` error so it's obvious where
the real adapter would slot in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


async def test_oauth_callback_stub_returns_not_implemented(client: TestClient):
    r = client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "abc", "state": "xyz", "redirect_uri": "http://localhost"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "oauth_not_implemented"


async def test_oauth_callback_unknown_provider_returns_400(client: TestClient):
    r = client.post(
        "/api/v1/auth/oauth/myspace/callback",
        json={"code": "abc", "state": "xyz", "redirect_uri": "http://localhost"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "unsupported_provider"


async def test_oauth_callback_missing_fields_returns_422(client: TestClient):
    r = client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "abc"},  # missing state + redirect_uri
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "request_validation_error"
