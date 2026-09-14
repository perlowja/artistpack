"""Publish-gate tests — every check isolated, every failure mode covered.

The four checks per ``docs/api-design.md`` §"`POST .../publish` — the gate":

    1. The generated manifest passes ``schema/pack.schema.json``.
    2. Every artwork's ``provenance.c2pa`` is ``true`` with a verified
       signature (Task 7 reduces this to "provenance_records row with
       verification_status == 'verified'").
    3. ``rights.license`` is a recognized value.
    4. Every artwork has non-empty ``attribution.display_name``.

Each check has a per-check failure test plus a happy-path test that
publishes and verifies the resulting status flip.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import (
    Artwork,
    ArtworkVariant,
    Artist,
    Pack,
    PackVersion,
    PackVersionStatus,
    ProvenanceRecord,
    ProvenanceVerificationStatus,
    User,
)


async def _add_artwork_and_publish_setup(
    db_session,
    *,
    license_override_id: str | None = None,
    attribution_name: str = "Test Artist",
    provenance_status: ProvenanceVerificationStatus | None = ProvenanceVerificationStatus.verified,
) -> dict:
    """Set up an artist + pack + draft + artwork, return useful refs."""

    owner = User(email="artist@example.com", display_name="A", role="artist")
    db_session.add(owner)
    await db_session.flush()
    artist = Artist(
        owner_user_id=owner.id,
        public_id=f"artist-{uuid.uuid4().hex[:6]}",
        name="Artist",
    )
    db_session.add(artist)
    await db_session.flush()

    pack = Pack(
        public_id=f"org.artistpack.test.{uuid.uuid4().hex[:6]}",
        artist_id=artist.id,
        title="Test Pack",
    )
    db_session.add(pack)
    await db_session.flush()

    manifest = {
        "artistpack": "0.1",
        "pack": {
            "id": pack.public_id,
            "title": pack.title,
            "version": "1.0.0",
        },
        "artist": {"id": artist.public_id, "name": artist.name},
        "rights": {
            "copyright": "Copyright 2026 Artist",
            "license": "artistpack-display-license-1.0",
        },
        "artworks": [
            {
                "id": f"placeholder-{uuid.uuid4().hex[:6]}",
                "title": "placeholder",
                "original": {
                    "file": "art/1.jpg",
                    "sha256": "a" * 64,
                    "width": 1920,
                    "height": 1080,
                    "mime_type": "image/jpeg",
                },
                "variants": [
                    {
                        "file": "art/1v.jpg",
                        "sha256": "b" * 64,
                        "width": 1920,
                        "height": 1080,
                    }
                ],
                "attribution": {"display_name": attribution_name},
                "provenance": {"c2pa": True, "manifest_file": "prov/1.c2pa"},
            }
        ],
    }
    from app.services.manifest_hash import recompute_and_set

    draft = PackVersion(
        pack_id=pack.id,
        version="1.0.0",
        manifest=manifest,
        status=PackVersionStatus.draft,
    )
    recompute_and_set(draft)
    db_session.add(draft)
    await db_session.flush()
    pack.current_draft_version_id = draft.id

    art = Artwork(
        pack_version_id=draft.id,
        public_id=f"art-{uuid.uuid4().hex[:6]}",
        title="Artwork 1",
        original_file="art/1.jpg",
        original_sha256="a" * 64,
        width=1920,
        height=1080,
        mime_type="image/jpeg",
        orientation="landscape",
        aspect_ratio="16:9",
        attribution_name=attribution_name,
    )
    if license_override_id is not None:
        art.license_id = uuid.UUID(license_override_id)
    db_session.add(art)
    await db_session.flush()
    db_session.add(
        ArtworkVariant(
            artwork_id=art.id,
            file="art/1v.jpg",
            sha256="b" * 64,
            width=1920,
            height=1080,
            mime_type="image/jpeg",
        )
    )
    if provenance_status is not None:
        db_session.add(
            ProvenanceRecord(
                artwork_id=art.id,
                manifest_file="prov/1.c2pa",
                signed_by="artistpack-signing-service",
                signed_at=datetime.now(timezone.utc),
                verification_status=provenance_status,
                verified_at=datetime.now(timezone.utc)
                if provenance_status == ProvenanceVerificationStatus.verified
                else None,
            )
        )
    await db_session.commit()
    return {
        "user_id": str(owner.id),
        "owner_user_id": str(owner.id),
        "artist_public_id": artist.public_id,
        "pack_id": str(pack.id),
        "pack_public_id": pack.public_id,
        "draft_id": str(draft.id),
        "artwork_id": str(art.id),
        "artwork_public_id": art.public_id,
    }


def _token_for(user_id: str) -> str:
    from app.auth.oauth import issue_session_token

    return issue_session_token(user_id)


# --- Happy path ---------------------------------------------------------------

async def test_publish_succeeds_when_all_checks_pass(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session)
    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "published"
    assert body["version"] == "1.0.0"
    assert body["manifest_sha256"]


# --- Check 1: schema validation ----------------------------------------------

async def test_check_1_schema_validation_rejects_invalid_manifest(client: TestClient, db_session):
    """Pack manifest missing required fields -> 422 with schema error path."""

    refs = await _add_artwork_and_publish_setup(db_session)
    from app.services.manifest_hash import recompute_and_set
    from app.db.models import PackVersion

    pv = await db_session.get(PackVersion, uuid.UUID(refs["draft_id"]))
    new_manifest = dict(pv.manifest)
    new_manifest["artist"] = {"id": "x"}  # missing 'name'
    pv.manifest = new_manifest
    recompute_and_set(pv)
    await db_session.commit()

    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "publish_validation_failed"
    paths = [e["path"] for e in body["error"]["details"]["errors"]]
    assert any("manifest" in p for p in paths), paths


# --- Check 2: verified provenance --------------------------------------------

async def test_check_2_missing_provenance_blocks_publish(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session, provenance_status=None)
    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    paths = [e["path"] for e in body["error"]["details"]["errors"]]
    assert any("provenance" in p for p in paths), paths


async def test_check_2_failed_provenance_blocks_publish(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(
        db_session,
        provenance_status=ProvenanceVerificationStatus.failed,
    )
    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
    body = r.json()
    paths = [e["path"] for e in body["error"]["details"]["errors"]]
    assert any("verification_status" in p for p in paths), paths


async def test_check_3_unrecognized_license_blocks_publish(client: TestClient, db_session):
    """Override the pack's manifest rights.license to an unknown value."""

    refs = await _add_artwork_and_publish_setup(db_session)
    from app.services.manifest_hash import recompute_and_set
    from app.db.models import PackVersion

    pv = await db_session.get(PackVersion, uuid.UUID(refs["draft_id"]))
    # Reassign the whole dict via attribute set so the ORM detects it
    # regardless of MutableDict tracking subtleties.
    new_manifest = dict(pv.manifest)
    new_manifest["rights"] = dict(new_manifest["rights"])
    new_manifest["rights"]["license"] = "NotARealLicense-9.9"
    pv.manifest = new_manifest
    recompute_and_set(pv)
    await db_session.commit()

    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    paths = [e["path"] for e in body["error"]["details"]["errors"]]
    assert any("rights.license" in p for p in paths), paths


async def test_check_4_empty_attribution_blocks_publish(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session, attribution_name="")
    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    paths = [e["path"] for e in body["error"]["details"]["errors"]]
    assert any("attribution.display_name" in p for p in paths), paths


async def test_check_4_whitespace_attribution_blocks_publish(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session, attribution_name="   ")
    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text


async def test_validation_endpoint_returns_same_errors_without_publishing(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session, provenance_status=None)
    token = _token_for(refs["owner_user_id"])
    r = client.get(
        f"/api/v1/packs/{refs['pack_public_id']}/validation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_id"] == refs["pack_public_id"]
    assert any("provenance" in e["path"] for e in body["errors"])


async def test_publish_unauthorized_returns_401(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session)
    r = client.post(f"/api/v1/packs/{refs['pack_public_id']}/publish")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_publish_wrong_owner_returns_403(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session)
    intruder = User(
        email=f"stranger-{uuid.uuid4().hex[:6]}@example.com",
        role="user",
    )
    db_session.add(intruder)
    await db_session.commit()
    other = _token_for(str(intruder.id))
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


async def test_publish_records_audit_log_entry(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session)
    token = _token_for(refs["owner_user_id"])
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    from app.db.models import AuditLog

    row = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "pack.publish")
        )
    ).scalar_one_or_none()
    assert row is not None, "expected an audit log row for the publish action"
    body = r.json()
    assert body["manifest_sha256"]
    assert row.detail is not None
    # The detail payload must include the same manifest_sha256 the API
    # returned to the client (load-bearing — see docs/database-schema.md
    # on the manifest_sha256 never-silently-drift invariant).
    assert row.detail["manifest_sha256"] == body["manifest_sha256"]


async def test_unpublish_reverts_to_draft(client: TestClient, db_session):
    refs = await _add_artwork_and_publish_setup(db_session)
    token = _token_for(refs["owner_user_id"])
    # publish
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # unpublish
    r2 = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/unpublish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "draft"


async def test_get_artwork_attribution_matches_published_manifest(client: TestClient, db_session):
    """End-to-end check that a published pack_version is fetchable and
    the attribution we set up round-trips through the public read endpoint."""

    refs = await _add_artwork_and_publish_setup(db_session, attribution_name="Round Trip Artist")
    token = _token_for(refs["owner_user_id"])
    # publish
    r = client.post(
        f"/api/v1/packs/{refs['pack_public_id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # fetch the public artwork endpoint via its public_id
    r2 = client.get(f"/api/v1/artworks/{refs['artwork_public_id']}")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["attribution_name"] == "Round Trip Artist"
