from fastapi import APIRouter

from src.api.v1 import admin, api_keys, crm, enrichment, webhooks

router = APIRouter(prefix="/v1")
router.include_router(api_keys.router)
router.include_router(crm.router)
router.include_router(webhooks.router)
router.include_router(admin.router)
router.include_router(enrichment.router)
router.include_router(pipeline.router)


@router.get("/me")
async def get_current_user_info():
    return {"service": "Mandate Finder API", "version": "0.1.0"}
