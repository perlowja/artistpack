"""Artists router: public list/get + authenticated CRUD."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import can_manage_artist, get_current_user
from app.core.errors import forbidden, not_found, unprocessable
from app.db import get_session
from app.db.models import Artist, ArtistLink, Pack, PackVersion, PackVersionStatus, User
from app.api.common import apply_cache, artist_manifest_url, cached_response_or_304, pack_manifest_url
from app.schemas import (
    ArtistCreateIn,
    ArtistLinkOut,
    ArtistOut,
    ArtistPatchIn,
    ArtistSummary,
    PackSummary,
    Page,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services.licenses import seed_licenses


router = APIRouter(prefix="/artists", tags=["artists"])


def _artist_to_summary(artist: Artist, base_url: str) -> ArtistSummary:
    return ArtistSummary(
        id=str(artist.id),
        public_id=artist.public_id,
        name=artist.name,
        avatar_url=None,  # avatar served via /storage/<key>; resolution is Phase 2
        website=artist.website,
    )


def _artist_to_out(artist: Artist, base_url: str, include_links: bool = True) -> ArtistOut:
    return ArtistOut(
        id=str(artist.id),
        public_id=artist.public_id,
        name=artist.name,
        bio=artist.bio,
        avatar_url=None,
        website=artist.website,
        patreon=artist.patreon,
        support_url=artist.support_url,
        socials=artist.socials,
        links=[ArtistLinkOut(kind=l.kind, url=l.url) for l in artist.links] if include_links else [],
        manifest_url=artist_manifest_url(base_url, artist.public_id),
        created_at=artist.created_at,
        updated_at=artist.updated_at,
    )


@router.get("", response_model=Page[ArtistSummary], summary="List artists (public)")
async def list_artists(
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> Page[ArtistSummary]:
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
    stmt = select(Artist).order_by(Artist.created_at, Artist.id)
    if last_id is not None:
        if last_created_at is not None:
            stmt = stmt.where(
                (Artist.created_at > last_created_at)
                | ((Artist.created_at == last_created_at) & (Artist.id > last_id))
            )
        else:
            stmt = stmt.where(Artist.id > last_id)
    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()

    items = [_artist_to_summary(a, base_url) for a in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last_row = rows[limit - 1]
        next_cursor = encode_cursor(
            {
                "last_id": str(last_row.id),
                "last_created_at": last_row.created_at.isoformat(),
            }
        )
    page = Page[ArtistSummary](items=items, next_cursor=next_cursor)
    apply_cache(response, page.model_dump_json().encode(), max_age=60)
    return page


@router.get("/{artist_id}", response_model=ArtistOut, summary="Get an artist (public)")
async def get_artist(
    artist_id: str,
    request: Request,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    session: AsyncSession = Depends(get_session),
) -> ArtistOut:
    base_url = str(request.base_url).rstrip("/")
    stmt = (
        select(Artist)
        .where(Artist.public_id == artist_id)
        .options(selectinload(Artist.links))
    )
    artist = (await session.execute(stmt)).scalar_one_or_none()
    if artist is None:
        raise not_found(message=f"No artist with public_id {artist_id!r}.")
    out = _artist_to_out(artist, base_url)
    serialized = out.model_dump_json().encode()
    return cached_response_or_304(serialized, max_age=300, if_none_match=if_none_match)


@router.get("/{artist_id}/packs", response_model=Page[PackSummary], summary="List an artist's packs")
async def list_artist_packs(
    artist_id: str,
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> Page[PackSummary]:
    base_url = str(request.base_url).rstrip("/")
    artist = (
        await session.execute(select(Artist).where(Artist.public_id == artist_id))
    ).scalar_one_or_none()
    if artist is None:
        raise not_found(message=f"No artist with public_id {artist_id!r}.")

    last_version_id: str | None = None
    if cursor:
        try:
            last_version_id = decode_cursor(cursor).get("last_version_id")
        except Exception:
            raise unprocessable("invalid_cursor", "Cursor could not be decoded.")

    # We paginate over PackVersion (so we can order by published version),
    # then map to PackSummary via the related pack.
    stmt = (
        select(PackVersion)
        .join(Pack, Pack.id == PackVersion.pack_id)
        .where(Pack.artist_id == artist.id)
        .where(PackVersion.status != PackVersionStatus.draft)
        .order_by(PackVersion.published_at.desc().nulls_last(), PackVersion.id.desc())
    )
    if last_version_id:
        stmt = stmt.where(PackVersion.id < last_version_id)
    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()

    # Load the related Pack rows.
    pack_ids = {r.pack_id for r in rows}
    packs = (
        await session.execute(select(Pack).where(Pack.id.in_(pack_ids)))
    ).scalars().all()
    packs_by_id = {p.id: p for p in packs}

    items: list[PackSummary] = []
    for v in rows[:limit]:
        p = packs_by_id.get(v.pack_id)
        if p is None:
            continue
        items.append(
            PackSummary(
                id=str(p.id),
                public_id=p.public_id,
                title=p.title,
                description=p.description,
                current_version=v.version,
                status=v.status.value,
                manifest_url=pack_manifest_url(base_url, artist.public_id, p.public_id),
                artist=_artist_to_summary(artist, base_url),
            )
        )

    next_cursor = (
        encode_cursor({"last_version_id": str(rows[limit - 1].id)}) if len(rows) > limit else None
    )
    page = Page[PackSummary](items=items, next_cursor=next_cursor)
    apply_cache(response, page.model_dump_json().encode(), max_age=60)
    return page


# --- Authenticated CRUD ------------------------------------------------------

@router.post("", response_model=ArtistOut, status_code=201, summary="Create artist profile")
async def create_artist(
    body: ArtistCreateIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ArtistOut:
    base_url = str(request.base_url).rstrip("/")
    # uniqueness
    existing = (
        await session.execute(select(Artist).where(Artist.public_id == body.public_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise unprocessable(
            "duplicate_public_id",
            f"An artist with public_id {body.public_id!r} already exists.",
        )

    await seed_licenses(session)

    artist = Artist(
        owner_user_id=user.id,
        public_id=body.public_id,
        name=body.name,
        bio=body.bio,
        website=body.website,
        patreon=body.patreon,
        support_url=body.support_url,
        socials=body.socials,
    )
    session.add(artist)
    await session.flush()
    if body.links:
        for link in body.links:
            session.add(ArtistLink(artist_id=artist.id, kind=link.kind, url=link.url))
    await session.commit()
    await session.refresh(artist, attribute_names=["links"])
    return _artist_to_out(artist, base_url)


@router.patch("/{artist_id}", response_model=ArtistOut, summary="Update artist profile")
async def patch_artist(
    artist_id: str,
    body: ArtistPatchIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ArtistOut:
    base_url = str(request.base_url).rstrip("/")
    artist = (
        await session.execute(
            select(Artist).where(Artist.public_id == artist_id).options(selectinload(Artist.links))
        )
    ).scalar_one_or_none()
    if artist is None:
        raise not_found(message=f"No artist with public_id {artist_id!r}.")
    if not can_manage_artist(user, artist.owner_user_id):
        raise forbidden()
    for field in ("name", "bio", "website", "patreon", "support_url"):
        new_value = getattr(body, field)
        if new_value is not None:
            setattr(artist, field, new_value)
    if body.socials is not None:
        artist.socials = body.socials
    await session.commit()
    await session.refresh(artist, attribute_names=["links"])
    return _artist_to_out(artist, base_url)


@router.post("/{artist_id}/avatar", status_code=202, summary="Upload artist avatar")
async def upload_avatar(
    artist_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    artist = (
        await session.execute(select(Artist).where(Artist.public_id == artist_id))
    ).scalar_one_or_none()
    if artist is None:
        raise not_found(message=f"No artist with public_id {artist_id!r}.")
    if not can_manage_artist(user, artist.owner_user_id):
        raise forbidden()
    # Stub: storage interface is wired, actual byte persistence happens in Phase 2.
    # We accept nothing here — avatar upload is multipart, but the byte
    # processing pipeline (resize, derivative) lives in Task 9.
    return {"artist_id": artist.public_id, "status": "received"}
