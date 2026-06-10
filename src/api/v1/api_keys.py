from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from src.core.pagination import CursorPage, paginate
from src.core.security import generate_api_key
from src.db.database import get_session
from src.db.models import APIKey
from src.middleware.rate_limit import authenticated_api_key

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


class APIKeyCreate(BaseModel):
    name: str
    scopes: list[str] = []
    tier: str = "solo"


class APIKeyUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    scopes: list[str] | None = None


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key: str | None = None
    scopes: list[str]
    tier: str
    last_used_at: datetime | None = None
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool


def _api_key_to_response(k: APIKey) -> dict:
    return APIKeyResponse(id=k.id, name=k.name, scopes=k.scopes, tier=k.tier, last_used_at=k.last_used_at, created_at=k.created_at, expires_at=k.expires_at, is_active=k.is_active).model_dump()


@router.get("", response_model=CursorPage)
async def list_api_keys(
    _api_key: APIKey = Depends(authenticated_api_key),
    cursor: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(APIKey).where(APIKey.is_active.is_(True)).order_by(APIKey.created_at.desc()).limit(limit + 1))
    keys = result.scalars().all()
    return paginate([_api_key_to_response(k) for k in keys], cursor=cursor, limit=limit)


@router.post("", response_model=APIKeyResponse, status_code=201)
async def create_api_key(body: APIKeyCreate, session: AsyncSession = Depends(get_session)):
    if not body.name.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Name is required")
    if body.tier not in ("solo", "professional", "agency"):
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Invalid tier")
    raw_key, key_hash = generate_api_key()
    api_key = APIKey(key_hash=key_hash, name=body.name, scopes=body.scopes, tier=body.tier)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return APIKeyResponse(id=api_key.id, name=api_key.name, key=raw_key, scopes=api_key.scopes, tier=api_key.tier, last_used_at=api_key.last_used_at, created_at=api_key.created_at, expires_at=api_key.expires_at, is_active=api_key.is_active)


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(key_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="API key not found")
    return APIKeyResponse(id=api_key.id, name=api_key.name, scopes=api_key.scopes, tier=api_key.tier, last_used_at=api_key.last_used_at, created_at=api_key.created_at, expires_at=api_key.expires_at, is_active=api_key.is_active)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(key_id: str, body: APIKeyUpdate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="API key not found")
    if body.name is not None:
        api_key.name = body.name
    if body.is_active is not None:
        api_key.is_active = body.is_active
    if body.scopes is not None:
        api_key.scopes = body.scopes
    await session.commit()
    await session.refresh(api_key)
    return APIKeyResponse(id=api_key.id, name=api_key.name, scopes=api_key.scopes, tier=api_key.tier, last_used_at=api_key.last_used_at, created_at=api_key.created_at, expires_at=api_key.expires_at, is_active=api_key.is_active)


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(key_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="API key not found")
    api_key.is_active = False
    await session.commit()


@router.patch("/{key_id}/touch", response_model=APIKeyResponse)
async def touch_api_key(key_id: str, session: AsyncSession = Depends(get_session)):
    now = datetime.now(UTC)
    await session.execute(update(APIKey).where(APIKey.id == key_id, APIKey.is_active.is_(True)).values(last_used_at=now))
    await session.commit()
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="API key not found")
    return APIKeyResponse(id=api_key.id, name=api_key.name, scopes=api_key.scopes, tier=api_key.tier, last_used_at=api_key.last_used_at, created_at=api_key.created_at, expires_at=api_key.expires_at, is_active=api_key.is_active)
