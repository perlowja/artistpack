"""Pagination + filter coverage for the public list endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.models import Artist, Pack, PackVersion, PackVersionStatus, User


SEED_COUNT = 30


async def _seed_packs(db_session, n: int = SEED_COUNT) -> list[str]:
    """Create n packs for a single test artist, return their public_ids."""

    owner = User(
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        display_name="U",
        role="artist",
    )
    db_session.add(owner)
    await db_session.flush()
    artist = Artist(
        owner_user_id=owner.id,
        public_id=f"artist-{uuid.uuid4().hex[:6]}",
        name="A",
    )
    db_session.add(artist)
    await db_session.flush()
    ids: list[str] = []
    for i in range(n):
        pid = f"org.test.pack.{i:03d}.{uuid.uuid4().hex[:4]}"
        p = Pack(
            public_id=pid,
            artist_id=artist.id,
            title=f"Pack {i:03d}",
        )
        db_session.add(p)
        await db_session.flush()
        v = PackVersion(
            pack_id=p.id,
            version="1.0.0",
            manifest={
                "artistpack": "0.1",
                "pack": {"id": pid, "title": p.title, "version": "1.0.0"},
                "artist": {"id": artist.public_id, "name": artist.name},
                "rights": {"copyright": "x", "license": "artistpack-display-license-1.0"},
                "artworks": [],
            },
            status=PackVersionStatus.published,
            published_at=datetime.now(timezone.utc) - timedelta(minutes=i),
        )
        db_session.add(v)
        ids.append(pid)
    await db_session.commit()
    return ids


async def test_list_packs_returns_cursor_paginated_results(client: TestClient, db_session):
    await _seed_packs(db_session)
    r = client.get("/api/v1/packs?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 10
    assert body["next_cursor"] is not None
    assert r.headers["etag"]
    assert r.headers["cache-control"].startswith("public, max-age=60")


async def test_list_packs_pagination_walks_through_all_results(client: TestClient, db_session):
    await _seed_packs(db_session)
    seen: set[str] = set()
    cursor: str | None = None
    pages = 0
    while True:
        url = "/api/v1/packs?limit=10"
        if cursor:
            url += f"&cursor={cursor}"
        r = client.get(url)
        assert r.status_code == 200
        body = r.json()
        if not body["items"]:
            break
        for it in body["items"]:
            seen.add(it["id"])
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
        if pages > 100:
            raise AssertionError("too many pages")
    assert pages >= 3, pages
    assert len(seen) >= SEED_COUNT, f"expected at least {SEED_COUNT} unique items, got {len(seen)}"


async def test_list_packs_filter_by_artist(client: TestClient, db_session):
    pids = await _seed_packs(db_session, 5)
    r = client.get(f"/api/v1/packs/{pids[0]}")
    assert r.status_code == 200
    body = r.json()
    artist_public_id = body["artist"]["public_id"]
    r2 = client.get(f"/api/v1/packs?artist={artist_public_id}&limit=50")
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) == 5
    for it in items:
        assert it["artist"]["public_id"] == artist_public_id


async def test_list_artists_paginates(client: TestClient, db_session):
    owner = User(email=f"u-{uuid.uuid4().hex[:6]}@example.com", role="artist")
    db_session.add(owner)
    await db_session.flush()
    for i in range(7):
        db_session.add(
            Artist(
                owner_user_id=owner.id,
                public_id=f"a-{i:03d}-{uuid.uuid4().hex[:4]}",
                name=f"A{i}",
            )
        )
    await db_session.commit()

    r = client.get("/api/v1/artists?limit=3")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is not None


async def test_etag_changes_when_content_changes(client: TestClient, db_session):
    pids = await _seed_packs(db_session, 1)
    r1 = client.get(f"/api/v1/packs/{pids[0]}")
    assert r1.status_code == 200
    etag1 = r1.headers["etag"]
    r2 = client.get(
        f"/api/v1/packs/{pids[0]}",
        headers={"If-None-Match": etag1},
    )
    assert r2.status_code == 304, r2.status_code


async def test_search_returns_mixed_pack_and_artwork_results(client: TestClient, db_session):
    await _seed_packs(db_session, 2)
    r = client.get("/api/v1/search?q=Pack&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 2
    assert all(it["type"] in ("pack", "artwork") for it in body["items"])


async def test_search_filter_by_orientation(client: TestClient, db_session):
    """``?orientation=landscape`` is the doc's filter set; verify
    it doesn't 500 and that artwork filtering happens (no artworks
    seeded here, so the artwork stream is empty)."""

    await _seed_packs(db_session, 2)
    r = client.get("/api/v1/search?orientation=landscape")
    assert r.status_code == 200


async def test_search_invalid_orientation_returns_422(client: TestClient):
    r = client.get("/api/v1/search?orientation=diagonal")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_orientation"


async def test_search_unknown_license_filter_returns_empty_artwork_stream(client: TestClient, db_session):
    """``?license=...`` with an unknown SPDX id should short-circuit the
    artwork stream to empty without 500ing."""

    await _seed_packs(db_session, 1)
    r = client.get("/api/v1/search?license=NotARealLicense-9.9")
    assert r.status_code == 200
    body = r.json()
    assert all(it["type"] == "pack" for it in body["items"])


async def test_search_invalid_cursor_returns_422(client: TestClient):
    r = client.get("/api/v1/search?cursor=not-a-real-cursor")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_cursor"


async def test_invalid_cursor_on_packs_list_returns_422(client: TestClient):
    r = client.get("/api/v1/packs?cursor=not-a-real-cursor")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_cursor"


async def test_invalid_limit_returns_422(client: TestClient):
    r = client.get("/api/v1/packs?limit=99999")
    assert r.status_code == 422


async def test_get_pack_404(client: TestClient):
    r = client.get("/api/v1/packs/org.does.not.exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_get_artwork_by_public_id(client: TestClient, db_session):
    """Public artwork endpoint should look up by either UUID or public_id."""

    owner = User(
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        role="artist",
    )
    db_session.add(owner)
    await db_session.flush()
    artist = Artist(
        owner_user_id=owner.id,
        public_id=f"a-{uuid.uuid4().hex[:4]}",
        name="A",
    )
    db_session.add(artist)
    await db_session.flush()
    pack = Pack(
        public_id=f"org.test.{uuid.uuid4().hex[:6]}",
        artist_id=artist.id,
        title="P",
    )
    db_session.add(pack)
    await db_session.flush()
    pv = PackVersion(
        pack_id=pack.id,
        version="1.0.0",
        manifest={
            "artistpack": "0.1",
            "pack": {"id": pack.public_id, "title": "P", "version": "1.0.0"},
            "artist": {"id": artist.public_id, "name": artist.name},
            "rights": {"copyright": "c", "license": "artistpack-display-license-1.0"},
            "artworks": [],
        },
        status=PackVersionStatus.published,
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(pv)
    await db_session.flush()

    from app.db.models import Artwork, ArtworkVariant

    art = Artwork(
        pack_version_id=pv.id,
        public_id="city-001",
        title="T",
        original_file="art/city.jpg",
        original_sha256="a" * 64,
        width=1920,
        height=1080,
        mime_type="image/jpeg",
        orientation="landscape",
        aspect_ratio="16:9",
        attribution_name="X",
    )
    db_session.add(art)
    await db_session.flush()
    db_session.add(
        ArtworkVariant(
            artwork_id=art.id,
            file="art/city.jpg",
            sha256="a" * 64,
            width=1920,
            height=1080,
            mime_type="image/jpeg",
        )
    )
    await db_session.commit()

    # By UUID
    r1 = client.get(f"/api/v1/artworks/{art.id}")
    assert r1.status_code == 200
    body = r1.json()
    assert body["public_id"] == "city-001"

    # By public_id
    r2 = client.get("/api/v1/artworks/city-001")
    assert r2.status_code == 200
    body = r2.json()
    assert body["public_id"] == "city-001"

    # Unknown id -> 404
    r3 = client.get("/api/v1/artworks/does-not-exist")
    assert r3.status_code == 404
