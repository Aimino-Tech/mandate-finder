from fastapi import APIRouter

from src.api.v1 import api_keys, compliance, webhooks

router = APIRouter(prefix="/v1")
router.include_router(api_keys.router)
router.include_router(webhooks.router)
router.include_router(compliance.router)


@router.get("/me")
async def get_current_user_info():
    return {"service": "Mandate Finder API", "version": "0.1.0"}
