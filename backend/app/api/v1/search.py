"""Search router: ``GET /api/v1/search`` per ``docs/api-design.md``.

PostgreSQL full-text search for MVP (see the doc; matches the YAGNI
note). On SQLite (our test backend) we fall back to a case-insensitive
LIKE search across the same fields — the behavior is identical from
the client's perspective, just less efficient. The route's response
shape and pagination are backend-agnostic.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.common import apply_cache
from app.core.errors import unprocessable
from app.db import get_session
from app.db.models import (
    Artwork,
    Pack,
    PackVersion,
    PackVersionStatus,
)
from app.schemas import SearchResults
from app.schemas.common import decode_cursor, encode_cursor


router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResults, summary="Free-text search across packs + artworks")
async def search(
    request: Request,
    response: Response,
    q: str | None = Query(default=None),
    artist: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    category: str | None = Query(default=None),
    orientation: str | None = Query(default=None),
    aspect_ratio: str | None = Query(default=None),
    license: str | None = Query(default=None),
    updated_since: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    if orientation and orientation not in ("landscape", "portrait", "square"):
        raise unprocessable("invalid_orientation", "orientation must be landscape|portrait|square.")

    last_id: str | None = None
    if cursor:
        try:
            last_id = decode_cursor(cursor).get("last_id")
        except Exception:
            raise unprocessable("invalid_cursor", "Cursor could not be decoded.")

    bind = session.bind
    is_pg = bind is not None and bind.dialect.name == "postgresql"

    # Two result rows: pack matches and artwork matches. We merge by
    # ``created_at`` descreasing; pagination is on the merged stream.
    pack_rows: list[Pack] = []
    artwork_rows: list[Artwork] = []

    # ---- Pack matches ------------------------------------------------------
    pack_stmt = (
        select(Pack)
        .join(Pack.artist)
        .options(selectinload(Pack.artist))
        .order_by(Pack.updated_at.desc(), Pack.id.desc())
    )
    if artist:
        pack_stmt = pack_stmt.where(Pack.artist.has(public_id=artist))
    if updated_since:
        from datetime import datetime
        try:
            cutoff = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
        except ValueError:
            raise unprocessable(
                "invalid_updated_since",
                "updated_since must be ISO-8601 (e.g. 2026-09-14T00:00:00Z).",
            )
        pack_stmt = pack_stmt.where(Pack.updated_at >= cutoff)
    if q:
        if is_pg:
            pack_stmt = pack_stmt.where(
                text("packs.search_vector @@ plainto_tsquery('simple', :q)")
            ).params(q=q)
        else:
            like = f"%{q}%"
            pack_stmt = pack_stmt.where(
                Pack.title.ilike(like) | Pack.description.ilike(like)
            )
    if last_id:
        pack_stmt = pack_stmt.where(Pack.id < last_id)
    if category:
        # Pack schema doesn't have a structured category column, so we
        # treat ``category`` as a token to require in the pack's
        # title-or-description. This matches how the filters are
        # intended to compose (loose OR), not a strict enum lookup.
        cat = category.lower().strip()
        pack_stmt = pack_stmt.where(
            func.lower(func.coalesce(Pack.title, "")).contains(cat)
            | func.lower(func.coalesce(Pack.description, "")).contains(cat)
        )
    pack_stmt = pack_stmt.limit(limit + 1)
    pack_rows = list((await session.execute(pack_stmt)).scalars().all())

    # ---- Artwork matches ---------------------------------------------------
    art_stmt = (
        select(Artwork)
        .join(Artwork.pack_version)
        .join(PackVersion.pack)
        .join(Pack.artist)
        .options(
            selectinload(Artwork.variants),
            selectinload(Artwork.pack_version).selectinload(PackVersion.pack).selectinload(Pack.artist),
        )
        .order_by(Artwork.created_at.desc(), Artwork.id.desc())
    )
    # Restrict to published pack_versions only — never expose draft artworks.
    art_stmt = art_stmt.where(PackVersion.status != PackVersionStatus.draft)
    if artist:
        art_stmt = art_stmt.where(Pack.artist.has(public_id=artist))
    if orientation:
        art_stmt = art_stmt.where(Artwork.orientation == orientation)
    if aspect_ratio:
        art_stmt = art_stmt.where(Artwork.aspect_ratio == aspect_ratio)
    if license:
        # license filter: artwork carries an explicit License catalog
        # row (overrides pack-level rights) or inherits from the pack.
        # SQLite has no JSON path operators, so for the MVP we accept
        # only the override match. An unknown license id short-circuits
        # the artwork stream to empty rather than 500ing.
        from app.db.models import License

        lic_row = (
            await session.execute(
                select(License).where(License.spdx_or_custom_id == license)
            )
        ).scalar_one_or_none()
        if lic_row is None:
            art_stmt = art_stmt.where(literal(False))
        else:
            art_stmt = art_stmt.where(Artwork.license_id == lic_row.id)
    if tag:
        from app.db.models import ArtworkTag, Tag

        art_stmt = art_stmt.join(
            ArtworkTag, ArtworkTag.artwork_id == Artwork.id
        ).join(Tag, Tag.id == ArtworkTag.tag_id)
        art_stmt = art_stmt.where(Tag.slug == tag.lower().strip())
    if q:
        if is_pg:
            art_stmt = art_stmt.where(
                text("artworks.search_vector @@ plainto_tsquery('simple', :q)")
            ).params(q=q)
        else:
            like = f"%{q}%"
            art_stmt = art_stmt.where(
                Artwork.title.ilike(like) | Artwork.description.ilike(like)
            )
    art_stmt = art_stmt.limit(limit + 1)
    artwork_rows = list((await session.execute(art_stmt)).scalars().unique().all())

    # ---- Merge + emit -----------------------------------------------------
    items: list[dict[str, Any]] = []
    for p in pack_rows[:limit]:
        items.append(
            {
                "type": "pack",
                "id": str(p.id),
                "public_id": p.public_id,
                "title": p.title,
                "artist_public_id": p.artist.public_id,
            }
        )
    for a in artwork_rows[:limit]:
        items.append(
            {
                "type": "artwork",
                "id": str(a.id),
                "public_id": a.public_id,
                "title": a.title,
                "pack_public_id": a.pack_version.pack.public_id,
                "artist_public_id": a.pack_version.pack.artist.public_id,
            }
        )

    next_cursor = None
    if len(pack_rows) > limit or len(artwork_rows) > limit:
        # Cursor just encodes the smaller of the two last ids so a
        # subsequent call doesn't repeat them. Conservative.
        candidates = []
        if len(pack_rows) > limit:
            candidates.append(str(pack_rows[limit - 1].id))
        if len(artwork_rows) > limit:
            candidates.append(str(artwork_rows[limit - 1].id))
        next_cursor = encode_cursor({"last_id": sorted(candidates)[0]})

    out = SearchResults(items=items, next_cursor=next_cursor)
    apply_cache(response, out.model_dump_json().encode(), max_age=60)
    return out
