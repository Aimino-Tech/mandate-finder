from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.config import settings
from mandate_finder.database import get_db
from mandate_finder.integrations.propelauth import PropelauthClient
from mandate_finder.models.organization import OrganizationMember, OrganizationRole
from mandate_finder.models.user import User

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_propelauth() -> PropelauthClient:
    return PropelauthClient()


def _dev_current_user() -> dict[str, Any]:
    return {
        "user_id": "local-dev-user",
        "email": "demo@mandate.local",
        "username": "Demo User",
    }


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    if settings.dev_auth_enabled:
        if token == settings.dev_auth_token:
            return _dev_current_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dev token",
        )

    if not settings.propelauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured. "
                "Set MANDATE_PROPELAUTH_API_KEY or run with ENVIRONMENT=local "
                "for built-in demo login."
            ),
        )

    client = PropelauthClient()
    try:
        return await client.validate_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e!s}",
        ) from e


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


async def ensure_app_user(
    db: AsyncSession, current_user: dict[str, Any]
) -> User:
    result = await db.execute(
        select(User).where(
            User.propelauth_user_id == current_user["user_id"]
        )
    )
    user = result.scalar_one_or_none()
    if user:
        return user
    username = (
        (current_user.get("username") or "").strip()
        or (current_user.get("email") or "user").split("@")[0]
        or "user"
    )
    email = (current_user.get("email") or "").strip() or "demo@mandate.local"
    user = User(
        username=username,
        email=email,
        propelauth_user_id=current_user["user_id"],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def current_user_id(
    db: DbSession, current_user: CurrentUser
) -> UUID:
    user = await ensure_app_user(db, current_user)
    return user.id


CurrentUserId = Annotated[UUID, Depends(current_user_id)]


async def get_current_role(
    db: DbSession, current_user: CurrentUser
) -> OrganizationRole:
    user = await ensure_app_user(db, current_user)
    if not user.organization_id:
        return OrganizationRole.ADMIN
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == user.organization_id,
        )
    )
    member = result.scalar_one_or_none()
    role = member.role if member else OrganizationRole.MEMBER
    return OrganizationRole(role)


CurrentUserRole = Annotated[OrganizationRole, Depends(get_current_role)]


def require_role(*roles: OrganizationRole) -> Callable[[CurrentUserRole], Any]:
    async def _require_role(current_role: CurrentUserRole) -> None:
        if current_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of {[r.value for r in roles]}",
            )

    return _require_role


require_admin: Any = Depends(require_role(OrganizationRole.ADMIN))
