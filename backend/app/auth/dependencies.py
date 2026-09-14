"""FastAPI auth dependencies + RBAC helpers."""

from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, unauthorized
from app.db import get_session
from app.db.models import User, UserRole
from app.auth.oauth import verify_session_token


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the current user from the ``Authorization: Bearer`` header.

    Raises 401 if the header is missing, malformed, or the token
    verifies to no live user.
    """

    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized()
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_session_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized()
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise unauthorized()
    return user


async def get_optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization, session=session)
    except Exception:
        return None


def require_roles(*allowed: UserRole):
    """Dependency factory that gates an endpoint by RBAC role."""

    allowed_set: set[UserRole] = set(allowed)

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            raise forbidden(
                code="role_required",
                message=f"Role {','.join(r.value for r in allowed_set)} required.",
                details={"actor_role": user.role.value, "allowed": [r.value for r in allowed]},
            )
        return user

    return _checker


def can_manage_artist(user: User, artist_owner_user_id: str) -> bool:
    """True if ``user`` can edit ``artist_owner_user_id``'s artist profile.

    Per ``docs/security-model.md``: an ``artist`` role controls only
    their own artists/packs; only moderator/admin can touch other
    people's.
    """

    if user.role in (UserRole.moderator, UserRole.administrator):
        return True
    return str(user.id) == str(artist_owner_user_id)
