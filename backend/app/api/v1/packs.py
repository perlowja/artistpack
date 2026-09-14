"""Packs router: public list/get + authenticated CRUD + publish gate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.common import apply_cache, cached_response_or_304, pack_manifest_url
from app.auth.dependencies import can_manage_artist, get_current_user
from app.core.errors import (
    APIError,
    forbidden,
    not_found,
    unprocessable,
)
from app.db import get_session
from app.db.models import (
    Artist,
    Pack,
    PackVersion,
    PackVersionStatus,
    User,
)
from app.schemas import (
    ArtistSummary,
    PackCreateIn,
    PackOut,
    PackPatchIn,
    PackSummary,
    Page,
    PublishError,
    PublishOut,
    PublishValidationOut,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services.manifest_hash import recompute_and_set
from app.services.publish_gate import check_pack_publishable


router = APIRouter(prefix="/packs", tags=["packs"])


def _pack_summary(pack: Pack, version: PackVersion | None, base_url: str) -> PackSummary:
    return PackSummary(
        id=str(pack.id),
        public_id=pack.public_id,
        title=pack.title,
        description=pack.description,
        current_version=version.version if version else None,
        status=version.status.value if version else None,
        manifest_url=pack_manifest_url(
            base_url, pack.artist.public_id, pack.public_id
        ),
        artist=ArtistSummary(
            id=str(pack.artist.id),
            public_id=pack.artist.public_id,
            name=pack.artist.name,
            website=pack.artist.website,
        ),
    )


def _pack_out(pack: Pack, version: PackVersion | None, base_url: str) -> PackOut:
    return PackOut(
        id=str(pack.id),
        public_id=pack.public_id,
        title=pack.title,
        description=pack.description,
        current_version=version.version if version else None,
        status=version.status.value if version else None,
        manifest_url=pack_manifest_url(base_url, pack.artist.public_id, pack.public_id),
        manifest_sha256=version.manifest_sha256 if version else None,
        artist=ArtistSummary(
            id=str(pack.artist.id),
            public_id=pack.artist.public_id,
            name=pack.artist.name,
            website=pack.artist.website,
        ),
        created_at=pack.created_at,
        updated_at=pack.updated_at,
    )


@router.get("", response_model=Page[PackSummary], summary="List packs (public)")
async def list_packs(
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    artist: str | None = Query(default=None),
    updated_since: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Page[PackSummary]:
    base_url = str(request.base_url).rstrip("/")
    last_id: str | None = None
    last_created_at: datetime | None = None
    if cursor:
        try:
            decoded = decode_cursor(cursor)
            last_id = decoded.get("last_id")
            iso = decoded.get("last_created_at")
            if iso:
                last_created_at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except Exception:
            raise unprocessable("invalid_cursor", "Cursor could not be decoded.")
    stmt = (
        select(Pack)
        .join(Pack.artist)
        .options(selectinload(Pack.artist))
        .order_by(Pack.created_at, Pack.id)
    )
    if artist:
        stmt = stmt.where(Pack.artist.has(public_id=artist))
    if updated_since:
        try:
            cutoff = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
        except ValueError:
            raise unprocessable(
                "invalid_updated_since",
                "updated_since must be ISO-8601 (e.g. 2026-09-14T00:00:00Z).",
            )
        stmt = stmt.where(Pack.updated_at >= cutoff)
    if last_id is not None:
        # Composite cursor: rows strictly after (created_at, id).
        # ``datetime`` is timezone-aware so the comparison is correct
        # against the tz-aware column.
        if last_created_at is not None:
            stmt = stmt.where(
                (Pack.created_at > last_created_at)
                | ((Pack.created_at == last_created_at) & (Pack.id > last_id))
            )
        else:
            stmt = stmt.where(Pack.id > last_id)
    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()

    # Load the most-recent non-draft version for each pack to populate status/version.
    pack_ids = [p.id for p in rows[:limit]]
    versions_by_pack: dict[Any, PackVersion] = {}
    if pack_ids:
        v_rows = (
            await session.execute(
                select(PackVersion)
                .where(PackVersion.pack_id.in_(pack_ids))
                .where(PackVersion.status != PackVersionStatus.draft)
                .order_by(PackVersion.published_at.desc().nulls_last(), PackVersion.created_at.desc())
            )
        ).scalars().all()
        for v in v_rows:
            versions_by_pack.setdefault(v.pack_id, v)

    items = [_pack_summary(p, versions_by_pack.get(p.id), base_url) for p in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last_row = rows[limit - 1]
        next_cursor = encode_cursor(
            {
                "last_id": str(last_row.id),
                "last_created_at": last_row.created_at.isoformat(),
            }
        )
    page = Page[PackSummary](items=items, next_cursor=next_cursor)
    apply_cache(response, page.model_dump_json().encode(), max_age=60)
    return page


@router.get("/{pack_id}", response_model=PackOut, summary="Get a pack (public)")
async def get_pack(
    pack_id: str,
    request: Request,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    session: AsyncSession = Depends(get_session),
) -> PackOut:
    base_url = str(request.base_url).rstrip("/")
    stmt = (
        select(Pack)
        .where(Pack.public_id == pack_id)
        .options(selectinload(Pack.artist))
    )
    pack = (await session.execute(stmt)).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    version = (
        await session.execute(
            select(PackVersion)
            .where(PackVersion.pack_id == pack.id)
            .where(PackVersion.status != PackVersionStatus.draft)
            .order_by(PackVersion.published_at.desc().nulls_last())
            .limit(1)
        )
    ).scalar_one_or_none()
    out = _pack_out(pack, version, base_url)
    serialized = out.model_dump_json().encode()
    return cached_response_or_304(serialized, max_age=300, if_none_match=if_none_match)


@router.get("/{pack_id}/validation", response_model=PublishValidationOut, summary="Pre-flight publish checks")
async def validation(
    pack_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PublishValidationOut:
    pack = (
        await session.execute(
            select(Pack).where(Pack.public_id == pack_id).options(selectinload(Pack.artist))
        )
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()
    draft = await _load_draft_pack_version(session, pack)
    if draft is None:
        return PublishValidationOut(pack_id=pack.public_id, version="", errors=[
            PublishError(path="pack", message="no draft pack_version exists yet"),
        ])
    errors = await check_pack_publishable(session, pack, draft)
    return PublishValidationOut(
        pack_id=pack.public_id,
        version=draft.version,
        errors=[PublishError(**e) for e in errors],
    )


# --- Authenticated CRUD ------------------------------------------------------

@router.post("", response_model=PackOut, status_code=201, summary="Create a draft pack")
async def create_pack(
    body: PackCreateIn,
    request: Request,
    artist_public_id: str = Query(..., description="public_id of the artist who owns this pack"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PackOut:
    base_url = str(request.base_url).rstrip("/")
    existing_pack = (
        await session.execute(select(Pack).where(Pack.public_id == body.public_id))
    ).scalar_one_or_none()
    if existing_pack is not None:
        raise unprocessable(
            "duplicate_public_id",
            f"A pack with public_id {body.public_id!r} already exists.",
        )
    artist_row = (
        await session.execute(
            select(Artist).where(Artist.public_id == artist_public_id)
        )
    ).scalar_one_or_none()
    if artist_row is None:
        raise not_found(message=f"No artist with public_id {artist_public_id!r}.")
    if not can_manage_artist(user, artist_row.owner_user_id):
        raise forbidden()

    pack = Pack(
        public_id=body.public_id,
        artist_id=artist_row.id,
        title=body.title,
        description=body.description,
    )
    session.add(pack)
    await session.flush()
    draft = PackVersion(
        pack_id=pack.id,
        version="0.0.0",
        manifest={
            "artistpack": "0.1",
            "pack": {"id": body.public_id, "title": body.title, "version": "0.0.0"},
            "artist": {"id": artist_row.public_id, "name": artist_row.name},
            "rights": {"copyright": "", "license": "artistpack-display-license-1.0"},
            "artworks": [],
        },
        status=PackVersionStatus.draft,
    )
    recompute_and_set(draft)
    session.add(draft)
    await session.flush()
    pack.current_draft_version_id = draft.id
    await session.commit()
    await session.refresh(pack, attribute_names=["artist"])
    return _pack_out(pack, draft, base_url)


@router.patch("/{pack_id}", response_model=PackOut, summary="Update a draft pack")
async def patch_pack(
    pack_id: str,
    body: PackPatchIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PackOut:
    base_url = str(request.base_url).rstrip("/")
    pack = (
        await session.execute(
            select(Pack).where(Pack.public_id == pack_id).options(selectinload(Pack.artist))
        )
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()
    draft = await _load_draft_pack_version(session, pack)
    if draft is None or draft.status != PackVersionStatus.draft:
        raise unprocessable(
            "not_editable",
            "Pack can only be edited while its current version is a draft.",
        )
    if body.title is not None:
        pack.title = body.title
        draft.manifest["pack"]["title"] = body.title
    if body.description is not None:
        pack.description = body.description
        draft.manifest["pack"]["description"] = body.description
    recompute_and_set(draft)
    await session.commit()
    return _pack_out(pack, draft, base_url)


@router.delete("/{pack_id}", status_code=204, summary="Delete a draft pack")
async def delete_pack(
    pack_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pack = (
        await session.execute(
            select(Pack).where(Pack.public_id == pack_id).options(selectinload(Pack.artist))
        )
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()
    draft = await _load_draft_pack_version(session, pack)
    if draft is not None and draft.status != PackVersionStatus.draft:
        raise unprocessable(
            "not_deletable",
            "Pack can only be deleted while its current version is a draft.",
        )
    await session.delete(pack)
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/{pack_id}/publish",
    response_model=PublishOut,
    summary="Run the publish gate; succeed only when all four checks pass",
)
async def publish_pack(
    pack_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PublishOut:
    pack = (
        await session.execute(
            select(Pack).where(Pack.public_id == pack_id).options(selectinload(Pack.artist))
        )
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()

    draft = await _load_draft_pack_version(session, pack)
    if draft is None:
        raise unprocessable("no_draft", "Pack has no draft version to publish.")
    if draft.status != PackVersionStatus.draft:
        raise unprocessable(
            "not_draft",
            f"Pack version is {draft.status.value!r}; only drafts can be published.",
        )

    errors = await check_pack_publishable(session, pack, draft)
    if errors:
        # Re-shape to ``details.errors[]`` per ``docs/api-design.md`` §Conventions.
        raise APIError(
            code="publish_validation_failed",
            message="Pack failed the publish gate. Resolve the errors and retry.",
            status_code=422,
            details={"errors": errors},
        )

    draft.status = PackVersionStatus.published
    draft.published_at = datetime.now(timezone.utc)
    # manifest_sha256 is set by recompute_and_set, and on Postgres it's
    # also enforced by the trigger — defense in depth.
    recompute_and_set(draft)

    # audit log
    from app.db.models import AuditLog

    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="pack.publish",
            target_type="pack",
            target_id=pack.id,
            detail={
                "pack_public_id": pack.public_id,
                "version": draft.version,
                "manifest_sha256": draft.manifest_sha256,
            },
        )
    )

    await session.commit()
    return PublishOut(
        pack_id=pack.public_id,
        version=draft.version,
        status=draft.status.value,
        published_at=draft.published_at,
        manifest_sha256=draft.manifest_sha256,
    )


@router.post("/{pack_id}/unpublish", response_model=PackOut, summary="Unpublish the current version")
async def unpublish_pack(
    pack_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PackOut:
    base_url = str(request.base_url).rstrip("/")
    pack = (
        await session.execute(
            select(Pack).where(Pack.public_id == pack_id).options(selectinload(Pack.artist))
        )
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()
    current = (
        await session.execute(
            select(PackVersion)
            .where(PackVersion.pack_id == pack.id)
            .where(PackVersion.status == PackVersionStatus.published)
            .order_by(PackVersion.published_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if current is None:
        raise unprocessable("not_published", "Pack has no published version to unpublish.")
    current.status = PackVersionStatus.draft
    current.published_at = None
    recompute_and_set(current)
    from app.db.models import AuditLog

    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="pack.unpublish",
            target_type="pack",
            target_id=pack.id,
            detail={"pack_public_id": pack.public_id, "version": current.version},
        )
    )
    await session.commit()
    return _pack_out(pack, current, base_url)


# --- Helpers -----------------------------------------------------------------

async def _load_draft_pack_version(session: AsyncSession, pack: Pack) -> PackVersion | None:
    if pack.current_draft_version_id is not None:
        v = await session.get(PackVersion, pack.current_draft_version_id)
        if v is not None:
            return v
    return (
        await session.execute(
            select(PackVersion)
            .where(PackVersion.pack_id == pack.id)
            .where(PackVersion.status == PackVersionStatus.draft)
            .order_by(PackVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
