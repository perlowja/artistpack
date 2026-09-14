"""Artworks router: pack-internal CRUD + public read endpoint."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.common import apply_cache, pack_manifest_url
from app.auth.dependencies import can_manage_artist, get_current_user
from app.core.errors import (
    APIError,
    not_found,
    unprocessable,
)
from app.db import get_session
from app.db.models import (
    Artwork,
    ArtworkVariant,
    AuditLog,
    Pack,
    PackVersion,
    PackVersionStatus,
    Tag,
    User,
)
from app.schemas import (
    ArtworkOut,
    ArtworkPatchIn,
    ArtworkVariantOut,
)
from app.services.ingest import (
    derive_aspect_ratio,
    derive_orientation,
    ingest_artwork,
)
from app.services.manifest_build import build_pack_manifest
from app.services.manifest_hash import recompute_and_set
from app.storage import get_storage


router = APIRouter(prefix="", tags=["artworks"])


def _variant_out(v: ArtworkVariant) -> ArtworkVariantOut:
    return ArtworkVariantOut(
        file=v.file,
        sha256=v.sha256,
        width=v.width,
        height=v.height,
        mime_type=v.mime_type,
        url=get_storage().public_url(v.file),
    )


def _artwork_out(
    art: Artwork, pack: Pack, base_url: str, pack_version: PackVersion
) -> ArtworkOut:
    return ArtworkOut(
        id=str(art.id),
        public_id=art.public_id,
        title=art.title,
        description=art.description,
        original_file=art.original_file,
        original_sha256=art.original_sha256,
        width=art.width,
        height=art.height,
        mime_type=art.mime_type,
        orientation=art.orientation,
        aspect_ratio=art.aspect_ratio,
        license=None,
        attribution_name=art.attribution_name,
        attribution_url=art.attribution_url,
        tags=[],  # joined-load below; for MVP we keep this simple
        variants=[_variant_out(v) for v in art.variants],
        pack_id=str(pack.id),
        pack_public_id=pack.public_id,
        manifest_url=pack_manifest_url(base_url, pack.artist.public_id, pack.public_id),
        display=art.display,
        palette=art.palette,
        created_at=art.created_at,
    )


# --- Public artwork read ------------------------------------------------------

@router.get("/artworks/{artwork_id}", response_model=ArtworkOut, summary="Get an artwork (public)")
async def get_artwork(
    artwork_id: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ArtworkOut:
    base_url = str(request.base_url).rstrip("/")
    # The spec's stable artwork identifier is the reverse-DNS-style
    # ``artwork.public_id`` (``spec/artistpack-0.1.md`` §3) — clients
    # discover artworks by that, not by the internal UUID. Accept the
    # UUID too because we sometimes surface it from list endpoints.
    if _looks_uuid(artwork_id):
        where = Artwork.id == uuid.UUID(artwork_id)
    else:
        where = Artwork.public_id == artwork_id
    art = (
        await session.execute(
            select(Artwork)
            .where(where)
            .options(
                selectinload(Artwork.variants),
                selectinload(Artwork.pack_version)
                .selectinload(PackVersion.pack)
                .selectinload(Pack.artist),
            )
        )
    ).scalar_one_or_none()
    if art is None:
        raise not_found(message=f"No artwork with id {artwork_id!r}.")

    pack = art.pack_version.pack
    out = _artwork_out(art, pack, base_url, art.pack_version)
    apply_cache(response, out.model_dump_json().encode(), max_age=300)
    return out


def _looks_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False


# --- Pack-internal CRUD ------------------------------------------------------

@router.post(
    "/packs/{pack_id}/artworks",
    response_model=ArtworkOut,
    status_code=201,
    summary="Upload an artwork to a pack",
)
async def upload_artwork(
    pack_id: str,
    request: Request,
    public_id: str = Form(...),
    title: str = Form(...),
    description: str | None = Form(default=None),
    attribution_name: str = Form(...),
    attribution_url: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ArtworkOut:
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

    draft = await _draft_for_pack(session, pack)
    if draft is None:
        raise unprocessable("no_draft", "Pack has no draft version to receive artworks.")

    # uniqueness within draft
    existing = (
        await session.execute(
            select(Artwork).where(Artwork.pack_version_id == draft.id, Artwork.public_id == public_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise unprocessable(
            "duplicate_public_id",
            f"An artwork with public_id {public_id!r} already exists in this draft.",
        )

    info = ingest_artwork(file.file)
    sha = info["sha256"]
    mime = info["mime_type"]
    width = info["width"]
    height = info["height"]

    # Storage: put the original under ``artworks/<pack_public_id>/<public_id>/original.<ext>``
    storage = get_storage()
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[mime]
    orig_key = f"artworks/{pack.public_id}/{public_id}/original.{ext}"
    storage.put(orig_key, info["data"], content_type=mime)

    # Stub variant: same file as the 1x variant. Real derivative
    # generation is Task 9.
    variant_key = f"artworks/{pack.public_id}/{public_id}/variants/original.{ext}"
    storage.put(variant_key, info["data"], content_type=mime)

    art = Artwork(
        pack_version_id=draft.id,
        public_id=public_id,
        title=title,
        description=description,
        original_file=orig_key,
        original_sha256=sha,
        width=width,
        height=height,
        mime_type=mime,
        orientation=derive_orientation(width, height),
        aspect_ratio=derive_aspect_ratio(width, height),
        attribution_name=attribution_name,
        attribution_url=attribution_url,
    )
    session.add(art)
    await session.flush()
    session.add(
        ArtworkVariant(
            artwork_id=art.id,
            file=variant_key,
            sha256=sha,
            width=width,
            height=height,
            mime_type=mime,
        )
    )
    # Refresh pack version's manifest with the new artwork and recompute sha.
    # Use selectinload chains so the subsequent build_pack_manifest does
    # not lazy-load any related rows (async sessions can't lazy-load).
    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload as _si

    draft = (
        await session.execute(
            _select(PackVersion)
            .where(PackVersion.id == draft.id)
            .options(
                _si(PackVersion.artworks).selectinload(Artwork.variants),
                _si(PackVersion.artworks).selectinload(Artwork.provenance),
            )
        )
    ).scalar_one()
    pack = (
        await session.execute(
            _select(Pack).where(Pack.id == pack.id).options(selectinload(Pack.artist))
        )
    ).scalar_one()
    draft.manifest = build_pack_manifest(pack, draft)
    recompute_and_set(draft)

    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="artwork.upload",
            target_type="artwork",
            target_id=art.id,
            detail={
                "pack_public_id": pack.public_id,
                "artwork_public_id": art.public_id,
            },
        )
    )
    await session.commit()
    # Re-load art with its variants so the response shape can be built
    # without lazy-loading (which is forbidden in async sessions).
    art = (
        await session.execute(
            _select(Artwork)
            .where(Artwork.id == art.id)
            .options(selectinload(Artwork.variants))
        )
    ).scalar_one()
    return _artwork_out(art, pack, base_url, draft)


@router.patch(
    "/packs/{pack_id}/artworks/{artwork_id}",
    response_model=ArtworkOut,
    summary="Update artwork metadata",
)
async def patch_artwork(
    pack_id: str,
    artwork_id: str,
    body: ArtworkPatchIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ArtworkOut:
    base_url = str(request.base_url).rstrip("/")
    pack, draft, art = await _load_artwork_in_pack(session, pack_id, artwork_id)
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if art is None:
        raise not_found(message=f"No artwork {artwork_id!r} in pack {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()

    if body.title is not None:
        art.title = body.title
    if body.description is not None:
        art.description = body.description
    if body.attribution_url is not None:
        art.attribution_url = body.attribution_url
    if body.tags is not None:
        await _replace_tags(session, art, body.tags)

    await session.refresh(draft, attribute_names=["artworks"])
    draft.manifest = build_pack_manifest(pack, draft)
    recompute_and_set(draft)
    await session.commit()
    await session.refresh(art, attribute_names=["variants"])
    return _artwork_out(art, pack, base_url, draft)


@router.delete(
    "/packs/{pack_id}/artworks/{artwork_id}",
    status_code=204,
    summary="Remove an artwork from a draft pack",
)
async def delete_artwork(
    pack_id: str,
    artwork_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pack, draft, art = await _load_artwork_in_pack(session, pack_id, artwork_id)
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    if art is None:
        raise not_found(message=f"No artwork {artwork_id!r} in pack {pack_id!r}.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()

    await session.delete(art)
    await session.flush()
    await session.refresh(draft, attribute_names=["artworks"])
    draft.manifest = build_pack_manifest(pack, draft)
    recompute_and_set(draft)

    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="artwork.delete",
            target_type="artwork",
            target_id=art.id,
            detail={"pack_public_id": pack.public_id, "artwork_public_id": art.public_id},
        )
    )
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/packs/{pack_id}/artworks/{artwork_id}/regenerate-derivatives",
    status_code=202,
    summary="Enqueue derivative regeneration (Task 9 stub)",
)
async def regenerate_derivatives(
    pack_id: str,
    artwork_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    pack, draft, art = await _load_artwork_in_pack(session, pack_id, artwork_id)
    if pack is None or art is None:
        raise not_found(message="Pack or artwork not found.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()
    # Real derivative pipeline is Task 9. Stub: enqueue a publishing_jobs
    # row and return its id so callers can poll.
    from app.db.models import PublishingJob, PublishingJobStatus

    job = PublishingJob(pack_version_id=draft.id, status=PublishingJobStatus.queued)
    session.add(job)
    await session.commit()
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "hint": "real derivative generation is Task 9 per docs/mvp-plan.md",
    }


@router.post(
    "/packs/{pack_id}/artworks/{artwork_id}/provenance/sign",
    status_code=202,
    summary="Stub C2PA sign endpoint (Task 9 boundary)",
)
async def sign_provenance(
    pack_id: str,
    artwork_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """**Task 9 boundary.** C2PA signing infrastructure is intentionally
    not implemented in Task 7 — see the publish gate docstring. This
    endpoint exists so the dashboard flow can complete without 404;
    for now it returns a clear "not_implemented" error.
    """

    pack, draft, art = await _load_artwork_in_pack(session, pack_id, artwork_id)
    if pack is None or art is None:
        raise not_found(message="Pack or artwork not found.")
    if not can_manage_artist(user, pack.artist.owner_user_id):
        raise forbidden()
    raise APIError(
        code="c2pa_sign_not_implemented",
        message=(
            "C2PA signing is Task 9 per docs/mvp-plan.md; "
            "this Task 7 build stubs the endpoint explicitly."
        ),
        status_code=501,
        details={"artwork_id": str(art.id)},
    )


# --- Helpers -----------------------------------------------------------------

async def _draft_for_pack(session: AsyncSession, pack: Pack) -> PackVersion | None:
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


async def _load_artwork_in_pack(
    session: AsyncSession, pack_id: str, artwork_id: str
) -> tuple[Pack | None, PackVersion | None, Artwork | None]:
    pack = (
        await session.execute(
            select(Pack).where(Pack.public_id == pack_id).options(selectinload(Pack.artist))
        )
    ).scalar_one_or_none()
    if pack is None:
        return None, None, None
    draft = await _draft_for_pack(session, pack)
    if draft is None:
        return pack, None, None
    # Accept either UUID or public_id.
    art: Artwork | None = None
    if _looks_uuid(artwork_id):
        art = (
            await session.execute(
                select(Artwork).where(Artwork.id == uuid.UUID(artwork_id), Artwork.pack_version_id == draft.id)
            )
        ).scalar_one_or_none()
    if art is None:
        art = (
            await session.execute(
                select(Artwork).where(
                    Artwork.public_id == artwork_id, Artwork.pack_version_id == draft.id
                )
            )
        ).scalar_one_or_none()
    return pack, draft, art


async def _replace_tags(session: AsyncSession, art: Artwork, tag_labels: list[str]) -> None:
    from app.db.models import ArtworkTag

    # Drop existing tags
    existing_links = (
        await session.execute(select(ArtworkTag).where(ArtworkTag.artwork_id == art.id))
    ).scalars().all()
    for link in existing_links:
        await session.delete(link)

    for label in tag_labels:
        slug = label.lower().strip().replace(" ", "-")
        if not slug:
            continue
        tag = (
            await session.execute(select(Tag).where(Tag.kind == "artwork", Tag.slug == slug))
        ).scalar_one_or_none()
        if tag is None:
            tag = Tag(kind="artwork", slug=slug, label=label)
            session.add(tag)
            await session.flush()
        session.add(ArtworkTag(artwork_id=art.id, tag_id=tag.id))
