"""OAuth callback stub + /me endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_provider, issue_session_token
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.errors import bad_request
from app.db import get_session
from app.db.models import Artist, AuditLog, OAuthAccount, User
from app.schemas import (
    ArtistSummary,
    MeOut,
    MePatchIn,
    OAuthCallbackIn,
    OAuthCallbackOut,
)


router = APIRouter(tags=["auth"])


@router.post(
    "/auth/oauth/{provider}/callback",
    response_model=OAuthCallbackOut,
    summary="OAuth provider callback stub (Task 7 boundary)",
)
async def oauth_callback(
    provider: str,
    body: OAuthCallbackIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OAuthCallbackOut:
    """Stub OAuth callback.

    For MVP this **does not** perform the actual provider token
    exchange. The :class:`StubOAuthProvider` is wired here to surface
    a clear error boundary; replace it with a real adapter
    implementing ``OAuthProvider.exchange`` (see ``app/auth/oauth.py``)
    to wire Google/GitHub for real.
    """

    adapter = get_provider(provider)
    info = await adapter.exchange(
        code=body.code, redirect_uri=body.redirect_uri, state=body.state
    )

    # Once the stub is replaced, the rest of this handler — find-or-
    # create the user, mint a session token — is real.
    existing = (
        await session.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == info.provider,
                OAuthAccount.provider_user_id == info.provider_user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        user = (
            await session.execute(select(User).where(User.id == existing.user_id))
        ).scalar_one()
    else:
        user = User(email=info.email, display_name=info.display_name)
        session.add(user)
        await session.flush()
        session.add(
            OAuthAccount(
                user_id=user.id, provider=info.provider, provider_user_id=info.provider_user_id
            )
        )
        session.add(
            AuditLog(
                actor_user_id=user.id,
                action="user.create",
                target_type="user",
                target_id=user.id,
                detail={"provider": info.provider},
            )
        )
        await session.commit()
        await session.refresh(user, attribute_names=["artists"])

    token = issue_session_token(str(user.id))
    me = await _me(user, session)
    return OAuthCallbackOut(
        user=me,
        token=token,
        expires_in=settings.oauth_session_ttl_seconds,
    )


@router.get("/me", response_model=MeOut, summary="Current user")
async def get_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    return await _me(user, session)


@router.patch("/me", response_model=MeOut, summary="Update current user")
async def patch_me(
    body: MePatchIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    if body.display_name is not None:
        user.display_name = body.display_name
    await session.commit()
    return await _me(user, session)


async def _me(user: User, session: AsyncSession) -> MeOut:
    artists = (
        await session.execute(
            select(Artist).where(Artist.owner_user_id == user.id)
        )
    ).scalars().all()
    return MeOut(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        artists=[
            ArtistSummary(
                id=str(a.id),
                public_id=a.public_id,
                name=a.name,
                website=a.website,
            )
            for a in artists
        ],
    )
