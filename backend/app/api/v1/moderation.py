"""Moderation/admin endpoints (per ``docs/api-design.md``).

Restricted to ``moderator``/``administrator`` roles per the doc.
Content removal never deletes the underlying audit trail — see
``docs/architecture.md``'s moderation principle.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.errors import not_found, unprocessable
from app.db import get_session
from app.db.models import (
    AuditLog,
    Pack,
    PackVersion,
    PackVersionStatus,
    Report,
    User,
    UserRole,
)
from app.schemas import (
    AuditLogOut,
    ReportIn,
    ReportOut,
    SuspendOut,
)


router = APIRouter(prefix="/admin", tags=["admin"])


# --- Reports -----------------------------------------------------------------

@router.post(
    "/reports",
    response_model=ReportOut,
    status_code=201,
    summary="File a moderation report (any authenticated user)",
)
async def create_report(
    body: ReportIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReportOut:
    report = Report(
        reporter_user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        detail=body.detail,
    )
    session.add(report)
    await session.commit()
    return ReportOut(
        id=report.id,
        target_type=report.target_type,
        target_id=str(report.target_id),
        reason=report.reason,
        created_at=report.created_at,
    )


@router.get(
    "/reports",
    response_model=list[ReportOut],
    summary="List reports (moderator+ only)",
)
async def list_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(require_roles(UserRole.moderator, UserRole.administrator)),
    session: AsyncSession = Depends(get_session),
) -> list[ReportOut]:
    stmt = select(Report).order_by(Report.created_at.desc()).limit(200)
    if status_filter:
        stmt = stmt.where(Report.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ReportOut(
            id=r.id,
            target_type=r.target_type,
            target_id=str(r.target_id),
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]


# --- Pack suspend / reinstate ------------------------------------------------

@router.post(
    "/packs/{pack_id}/suspend",
    response_model=SuspendOut,
    summary="Suspend a pack (moderator+ only)",
)
async def suspend_pack(
    pack_id: str,
    request: Request,
    reason: str | None = Query(default=None),
    user: User = Depends(require_roles(UserRole.moderator, UserRole.administrator)),
    session: AsyncSession = Depends(get_session),
) -> SuspendOut:
    pack = (
        await session.execute(select(Pack).where(Pack.public_id == pack_id))
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")

    pv = (
        await session.execute(
            select(PackVersion)
            .where(PackVersion.pack_id == pack.id)
            .where(PackVersion.status == PackVersionStatus.published)
            .order_by(PackVersion.published_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if pv is None:
        raise unprocessable("not_published", "Pack has no published version to suspend.")
    pv.status = PackVersionStatus.suspended
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="pack.suspend",
            target_type="pack",
            target_id=pack.id,
            detail={"pack_public_id": pack.public_id, "reason": reason},
        )
    )
    await session.commit()
    return SuspendOut(pack_id=pack.public_id, status=pv.status.value, reason=reason)


@router.post(
    "/packs/{pack_id}/reinstate",
    response_model=SuspendOut,
    summary="Reinstate a suspended pack",
)
async def reinstate_pack(
    pack_id: str,
    user: User = Depends(require_roles(UserRole.moderator, UserRole.administrator)),
    session: AsyncSession = Depends(get_session),
) -> SuspendOut:
    pack = (
        await session.execute(select(Pack).where(Pack.public_id == pack_id))
    ).scalar_one_or_none()
    if pack is None:
        raise not_found(message=f"No pack with public_id {pack_id!r}.")
    pv = (
        await session.execute(
            select(PackVersion)
            .where(PackVersion.pack_id == pack.id)
            .where(PackVersion.status == PackVersionStatus.suspended)
            .order_by(PackVersion.published_at.desc().nulls_last())
            .limit(1)
        )
    ).scalar_one_or_none()
    if pv is None:
        raise unprocessable("not_suspended", "Pack has no suspended version to reinstate.")
    pv.status = PackVersionStatus.published
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="pack.reinstate",
            target_type="pack",
            target_id=pack.id,
            detail={"pack_public_id": pack.public_id},
        )
    )
    await session.commit()
    return SuspendOut(pack_id=pack.public_id, status=pv.status.value)


# --- Audit log ---------------------------------------------------------------

@router.get(
    "/audit-log",
    response_model=list[AuditLogOut],
    summary="Recent audit log entries (administrator only)",
)
async def audit_log(
    limit: int = Query(default=200, ge=1, le=1000),
    user: User = Depends(require_roles(UserRole.administrator)),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogOut]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AuditLogOut(
            id=r.id,
            actor_user_id=str(r.actor_user_id) if r.actor_user_id else None,
            action=r.action,
            target_type=r.target_type,
            target_id=str(r.target_id),
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
