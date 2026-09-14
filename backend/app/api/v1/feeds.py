"""Feeds router: public list/get + admin/moderation maintain endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.common import apply_cache, feed_manifest_url, pack_manifest_url
from app.auth.dependencies import require_roles
from app.core.errors import not_found, unprocessable
from app.db import get_session
from app.db.models import (
    AuditLog,
    Feed,
    FeedItem,
    Pack,
    PackVersion,
    User,
    UserRole,
)
from app.schemas import (
    ArtistSummary,
    FeedCreateIn,
    FeedOut,
    FeedSummary,
    PackSummary,
    Page,
)
from app.schemas.common import decode_cursor, encode_cursor


# Two routers: public reads at /feeds, admin CRUD below.
public_router = APIRouter(prefix="/feeds", tags=["feeds"])
admin_router = APIRouter(prefix="/admin/feeds", tags=["feeds (admin)"])


def _feed_to_summary(feed: Feed) -> FeedSummary:
    return FeedSummary(
        id=str(feed.id),
        public_id=feed.public_id,
        title=feed.title,
        description=feed.description,
        updated_at=feed.updated_at,
    )


@public_router.get("", response_model=Page[FeedSummary], summary="List feeds (public)")
async def list_feeds(
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> Page[FeedSummary]:
    last_id: str | None = None
    if cursor:
        try:
            last_id = decode_cursor(cursor).get("last_id")
        except Exception:
            raise unprocessable("invalid_cursor", "Cursor could not be decoded.")
    stmt = select(Feed).order_by(Feed.updated_at.desc(), Feed.id.desc())
    if last_id:
        stmt = stmt.where(Feed.id < last_id)
    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    items = [_feed_to_summary(f) for f in rows[:limit]]
    next_cursor = (
        encode_cursor({"last_id": str(rows[limit - 1].id)}) if len(rows) > limit else None
    )
    page = Page[FeedSummary](items=items, next_cursor=next_cursor)
    apply_cache(response, page.model_dump_json().encode(), max_age=60)
    return page


@public_router.get("/{feed_id}", response_model=FeedOut, summary="Get a feed (public)")
async def get_feed(
    feed_id: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> FeedOut:
    base_url = str(request.base_url).rstrip("/")
    feed = (
        await session.execute(
            select(Feed).where(Feed.public_id == feed_id).options(selectinload(Feed.items))
        )
    ).scalar_one_or_none()
    if feed is None:
        raise not_found(message=f"No feed with public_id {feed_id!r}.")

    pack_version_ids = [i.pack_version_id for i in feed.items]
    pack_versions = (
        await session.execute(
            select(PackVersion).where(PackVersion.id.in_(pack_version_ids))
        )
    ).scalars().all() if pack_version_ids else []
    packs_by_id = {}
    if pack_versions:
        p_ids = {v.pack_id for v in pack_versions}
        packs = (
            await session.execute(select(Pack).where(Pack.id.in_(p_ids)).options(selectinload(Pack.artist)))
        ).scalars().all()
        packs_by_id = {p.id: p for p in packs}

    items = []
    for fi in feed.items:
        v = next((x for x in pack_versions if x.id == fi.pack_version_id), None)
        if v is None:
            continue
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
                manifest_url=pack_manifest_url(base_url, p.artist.public_id, p.public_id),
                artist=ArtistSummary(
                    id=str(p.artist.id),
                    public_id=p.artist.public_id,
                    name=p.artist.name,
                    website=p.artist.website,
                ),
            )
        )

    out = FeedOut(
        id=str(feed.id),
        public_id=feed.public_id,
        title=feed.title,
        description=feed.description,
        updated_at=feed.updated_at,
        manifest_url=feed_manifest_url(base_url, feed.public_id),
        items=items,
    )
    apply_cache(response, out.model_dump_json().encode(), max_age=300)
    return out


# --- Admin / moderation -----------------------------------------------------

@admin_router.post(
    "",
    response_model=FeedOut,
    status_code=201,
    summary="Create a feed (moderator+ only)",
)
async def create_feed(
    body: FeedCreateIn,
    request: Request,
    user: User = Depends(require_roles(UserRole.moderator, UserRole.administrator)),
    session: AsyncSession = Depends(get_session),
) -> FeedOut:
    base_url = str(request.base_url).rstrip("/")
    existing = (
        await session.execute(select(Feed).where(Feed.public_id == body.public_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise unprocessable(
            "duplicate_public_id",
            f"A feed with public_id {body.public_id!r} already exists.",
        )
    feed = Feed(
        public_id=body.public_id,
        title=body.title,
        description=body.description,
    )
    session.add(feed)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="feed.create",
            target_type="feed",
            target_id=feed.id,
            detail={"feed_public_id": body.public_id},
        )
    )
    await session.commit()
    out = FeedOut(
        id=str(feed.id),
        public_id=feed.public_id,
        title=feed.title,
        description=feed.description,
        updated_at=feed.updated_at,
        manifest_url=feed_manifest_url(base_url, feed.public_id),
        items=[],
    )
    return out


@admin_router.post(
    "/{feed_id}/items",
    status_code=201,
    summary="Add a pack_version to a feed",
)
async def add_feed_item(
    feed_id: str,
    pack_version_id: str,
    request: Request,
    position: int = Query(default=0),
    user: User = Depends(require_roles(UserRole.moderator, UserRole.administrator)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    feed = (
        await session.execute(select(Feed).where(Feed.public_id == feed_id))
    ).scalar_one_or_none()
    if feed is None:
        raise not_found(message=f"No feed with public_id {feed_id!r}.")
    # pack_version_id may be the UUID.
    import uuid as _uuid

    try:
        pv_uuid = _uuid.UUID(pack_version_id)
    except ValueError:
        raise unprocessable("invalid_pack_version_id", "pack_version_id must be a UUID.")
    pv = await session.get(PackVersion, pv_uuid)
    if pv is None:
        raise not_found(message="pack_version not found.")
    item = FeedItem(feed_id=feed.id, pack_version_id=pv.id, position=position)
    session.add(item)
    feed.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"feed_id": feed.public_id, "pack_version_id": str(pv.id), "position": position}
