from __future__ import annotations

import uuid
from typing import Any, Protocol

from fastapi import Depends, HTTPException, status
from propelauth_fastapi import init_auth

from src.config import settings

auth = init_auth(settings.propelauth_auth_url, settings.propelauth_api_key)


class UserInfo(Protocol):
    user_id: str
    email: str
    org_id: str | None


async def get_current_user(
    user: Any = Depends(auth.require_user),  # noqa: B008
) -> UserInfo:
    return user


async def get_optional_user(
    user: Any = Depends(auth.optional_user),  # noqa: B008
) -> UserInfo | None:
    return user


def parse_user_id(user: UserInfo) -> uuid.UUID:
    try:
        return uuid.UUID(user.user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format",
        ) from None
