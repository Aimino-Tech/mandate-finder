from fastapi import Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from src.db.models import APIKey
from src.middleware.rate_limit import authenticated_api_key

ADMIN_TIERS = {"agency"}


async def require_admin(api_key: APIKey = Depends(authenticated_api_key)) -> APIKey:
    if api_key.tier not in ADMIN_TIERS:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Requires admin-level API key (agency tier)",
        )
    return api_key
