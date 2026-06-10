from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from mandate_finder.config import settings
from mandate_finder.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthPublicConfig(BaseModel):
    demo_login_available: bool
    propelauth_configured: bool
    propelauth_login_url: str | None


@router.get("/config", response_model=AuthPublicConfig)
async def auth_public_config() -> AuthPublicConfig:
    base = settings.propelauth_auth_url.rstrip("/")
    return AuthPublicConfig(
        demo_login_available=settings.demo_login_available,
        propelauth_configured=settings.propelauth_configured,
        propelauth_login_url=(
            f"{base}/en/login" if settings.propelauth_configured else None
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest) -> TokenResponse:
    if settings.dev_auth_enabled and not settings.propelauth_configured:
        return TokenResponse(
            token=settings.dev_auth_token, user_id="local-dev-user"
        )

    if not settings.propelauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured. Set MANDATE_PROPELAUTH_API_KEY or use local demo (ENVIRONMENT=local).",
        )

    from mandate_finder.integrations.propelauth import PropelauthClient

    client = PropelauthClient()
    try:
        resp = await client.login(data.email, data.password)
        return TokenResponse(
            token=resp["access_token"], user_id=resp["user_id"]
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from None


@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/register", response_model=TokenResponse)
async def register(data: LoginRequest) -> TokenResponse:
    if not settings.propelauth_configured:
        if settings.dev_auth_enabled:
            return TokenResponse(
                token=settings.dev_auth_token, user_id="local-dev-user"
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured.",
        )

    from mandate_finder.integrations.propelauth import PropelauthClient

    client = PropelauthClient()
    try:
        resp = await client.create_user(data.email, data.password, data.email.split("@")[0])
        return TokenResponse(
            token=resp.get("access_token", ""),
            user_id=resp.get("user_id", ""),
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. User may already exist.",
        ) from None
