"""Unit tests for the focused service-layer modules.

These don't exercise HTTP, just the underlying functions:

* :mod:`app.services.manifest_hash` — canonical SHA-256 over the
  manifest dict; the integrity-floor that ``pack_versions`` rows must
  match. Tested for ordering-invariance and null-dropping behavior.
* :mod:`app.services.ingest` — image MIME sniffing + decompression-bomb
  guard.
* :mod:`app.auth.oauth` — the StubOAuthProvider boundary.
"""

from __future__ import annotations

import pytest

from app.auth.oauth import StubOAuthProvider, issue_session_token, verify_session_token
from app.services.ingest import (
    derive_aspect_ratio,
    derive_orientation,
    sniff_mime,
)
from app.services.manifest_hash import (
    canonical_manifest_bytes,
    compute_manifest_sha256,
)


# --- manifest_hash -----------------------------------------------------------

def test_canonical_serialization_is_key_order_independent():
    a = {"b": 1, "a": 2, "c": 3}
    b = {"c": 3, "a": 2, "b": 1}
    assert canonical_manifest_bytes(a) == canonical_manifest_bytes(b)


def test_canonical_serialization_drops_null_values():
    with_nulls = {"a": 1, "b": None, "c": 3}
    without = {"a": 1, "c": 3}
    assert canonical_manifest_bytes(with_nulls) == canonical_manifest_bytes(without)


def test_canonical_serialization_handles_nested_dicts_and_lists():
    nested = {"pack": {"title": "Hello", "version": "1.0.0"}, "tags": ["x", "y"]}
    serialized = canonical_manifest_bytes(nested)
    assert serialized.startswith(b"{")
    assert b'"pack"' in serialized
    assert b'"tags"' in serialized


def test_hash_matches_for_equivalent_documents():
    doc1 = {"pack": {"id": "x", "title": "T"}, "version": 1}
    doc2 = {"version": 1, "pack": {"title": "T", "id": "x"}}
    assert compute_manifest_sha256(doc1) == compute_manifest_sha256(doc2)


def test_hash_differs_for_different_content():
    a = compute_manifest_sha256({"x": 1})
    b = compute_manifest_sha256({"x": 2})
    assert a != b


def test_hash_is_64_char_lowercase_hex():
    h = compute_manifest_sha256({"hello": "world"})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# --- ingest -------------------------------------------------------------------

def test_derive_orientation_landscape():
    assert derive_orientation(1920, 1080) == "landscape"


def test_derive_orientation_portrait():
    assert derive_orientation(1080, 1920) == "portrait"


def test_derive_orientation_square():
    assert derive_orientation(1024, 1024) == "square"


def test_derive_aspect_ratio_reduces_to_lowest_terms():
    assert derive_aspect_ratio(1920, 1080) == "16:9"
    assert derive_aspect_ratio(1024, 1024) == "1:1"
    assert derive_aspect_ratio(3840, 2160) == "16:9"


def test_png_bytes_sniff_to_png(png_bytes):
    assert sniff_mime(png_bytes) == "image/png"


def test_jpeg_bytes_sniff_to_jpeg(jpeg_bytes):
    assert sniff_mime(jpeg_bytes) == "image/jpeg"


def test_unknown_bytes_sniff_to_octet_stream():
    assert sniff_mime(b"not really an image") == "application/octet-stream"


# --- OAuth stub ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_stub_oauth_exchange_raises_clear_error():
    from app.core.errors import APIError

    provider = StubOAuthProvider("google")
    with pytest.raises(APIError) as exc_info:
        await provider.exchange(code="abc", redirect_uri="http://x", state="y")
    assert exc_info.value.detail["error"]["code"] == "oauth_not_implemented"


@pytest.mark.asyncio
async def test_stub_oauth_authorize_returns_about_blank():
    provider = StubOAuthProvider("github")
    url = await provider.build_authorize_url(state="xyz", redirect_uri="http://x")
    assert url.startswith("about:blank")


def test_session_token_round_trip():
    token = issue_session_token("user-123")
    payload = verify_session_token(token)
    assert payload["sub"] == "user-123"


def test_session_token_invalid_signature_rejected():
    token = issue_session_token("user-123")
    bad = token[:-2] + ("A" if token[-1] != "A" else "B") + token[-1]
    from app.core.errors import APIError

    with pytest.raises(APIError):
        verify_session_token(bad)
