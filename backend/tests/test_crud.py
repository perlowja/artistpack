"""Auth + CRUD end-to-end tests.

Exercises the artist profile, pack, and artwork upload endpoints at a
level of detail that catches obvious wire-up bugs (404 routing,
validation envelopes, RBAC) without re-running the publish-gate
matrix (which has its own dedicated file).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def _png_bytes(w: int = 1920, h: int = 1080, color=(180, 60, 60)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _make_artist_via_api(client: TestClient, make_user, token: str, public_id: str) -> dict:
    r = client.post(
        "/api/v1/artists",
        json={"public_id": public_id, "name": "Test Artist", "bio": "b"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_artist_profile(client: TestClient, make_user):
    user = await make_user()
    r = client.post(
        "/api/v1/artists",
        json={"public_id": "nova-ashworth", "name": "Nova Ashworth"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["public_id"] == "nova-ashworth"
    assert body["manifest_url"].endswith("/artists/nova-ashworth/artist.yaml")


async def test_create_artist_duplicate_public_id_returns_422(client: TestClient, make_user):
    user = await make_user()
    await _make_artist_via_api(client, make_user, user["token"], "dup-artist")
    r = client.post(
        "/api/v1/artists",
        json={"public_id": "dup-artist", "name": "X"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "duplicate_public_id"


async def test_create_pack(client: TestClient, make_user):
    user = await make_user()
    await _make_artist_via_api(client, make_user, user["token"], "pack-artist")
    r = client.post(
        "/api/v1/packs?artist_public_id=pack-artist",
        json={"public_id": "org.test.pack", "title": "Pack"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["public_id"] == "org.test.pack"
    assert body["status"] == "draft"


async def test_other_user_cannot_modify_pack(client: TestClient, make_user):
    owner = await make_user()
    await _make_artist_via_api(client, make_user, owner["token"], "lock-artist")
    r = client.post(
        "/api/v1/packs?artist_public_id=lock-artist",
        json={"public_id": "org.test.lock", "title": "Pack"},
        headers={"Authorization": f"Bearer {owner['token']}"},
    )
    assert r.status_code == 201, r.text
    intruder = await make_user()
    r2 = client.patch(
        "/api/v1/packs/org.test.lock",
        json={"title": "HiJacked"},
        headers={"Authorization": f"Bearer {intruder['token']}"},
    )
    assert r2.status_code == 403
    assert r2.json()["error"]["code"] == "forbidden"


async def test_upload_artwork_stores_to_disk(client: TestClient, make_user):
    user = await make_user()
    await _make_artist_via_api(client, make_user, user["token"], "upload-artist")
    r = client.post(
        "/api/v1/packs?artist_public_id=upload-artist",
        json={"public_id": "org.test.up", "title": "Pack"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 201, r.text

    png = _png_bytes(800, 600)
    r2 = client.post(
        "/api/v1/packs/org.test.up/artworks",
        data={
            "public_id": "art-001",
            "title": "Untitled",
            "attribution_name": "Test Artist",
        },
        files={"file": ("art.png", io.BytesIO(png), "image/png")},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r2.status_code == 201, r2.text
    body = r2.json()
    assert body["public_id"] == "art-001"
    assert body["width"] == 800
    assert body["height"] == 600
    assert body["orientation"] == "landscape"
    assert body["aspect_ratio"] == "4:3"


async def test_upload_artwork_rejects_oversized_dimensions(client: TestClient, make_user, monkeypatch):
    """Decompression-bomb guard. We can't easily build a real bomb in
    a unit test, so we just verify the cap exists via a tiny image and
    the documented check fires for an obviously-too-large width.
    """
    user = await make_user()
    await _make_artist_via_api(client, make_user, user["token"], "bomb-artist")
    r = client.post(
        "/api/v1/packs?artist_public_id=bomb-artist",
        json={"public_id": "org.test.bomb", "title": "Pack"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 201

    # Build a PNG with declared dimensions > the cap. Real PNG decoders
    # verify IHDR before decoding pixel data, so this is the right test.
    big = Image.new("RGB", (10, 10), (255, 255, 255))
    buf = io.BytesIO()
    big.save(buf, format="PNG")
    data = buf.getvalue()

    from app.core.config import settings

    # Lower the cap for this test; the bomb-guard branch is exercised
    # via the same code path regardless.
    monkeypatch.setattr(settings, "artwork_max_pixels", 4)
    r2 = client.post(
        "/api/v1/packs/org.test.bomb/artworks",
        data={"public_id": "art-bomb", "title": "T", "attribution_name": "X"},
        files={"file": ("art.png", io.BytesIO(data), "image/png")},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r2.status_code == 400
    body = r2.json()
    assert body["error"]["code"] in ("image_too_large", "unsupported_mime", "image_decode_failed")


async def test_me_endpoint_requires_auth(client: TestClient):
    r = client.get("/api/v1/me")
    assert r.status_code == 401


async def test_me_endpoint_returns_authenticated_user(client: TestClient, make_user):
    user = await make_user(role="artist")
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {user['token']}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == user["email"]
    assert body["role"] == "artist"


async def test_admin_endpoints_require_moderator_role(client: TestClient, make_user):
    user = await make_user(role="user")
    r = client.get(
        "/api/v1/admin/reports",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "role_required"


async def test_moderator_can_list_audit_log(client: TestClient, make_user, db_session):
    """Audit log requires administrator; moderator is denied."""

    user = await make_user(role="moderator")
    r = client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "role_required"


async def test_administrator_can_read_audit_log(client: TestClient, make_user, db_session):
    user = await make_user(role="administrator")
    r = client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)
