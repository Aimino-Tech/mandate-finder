from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from src.core.security import hash_api_key
from src.db.database import get_session
from src.db.models import APIKey

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> APIKey:
    if credentials is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")
    key_hash = hash_api_key(credentials.credentials)
    result = await session.execute(select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True)))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API key")
    if api_key.expires_at and api_key.expires_at < __import__("datetime").datetime.now(__import__("datetime").timezone.utc):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="API key has expired")
    request.state.api_key_id = api_key.id
    request.state.api_key_tier = api_key.tier
    return api_key
