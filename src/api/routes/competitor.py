from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.services.competitor_insights import (
    get_alternative_companies,
    get_competitor_insight,
    get_signal_timeline,
)

router = APIRouter(prefix="/api/companies", tags=["competitor-insights"])


@router.get("/{company_id}/insights")
async def competitor_insight(
    company_id: str,
    db: AsyncSession = Depends(get_session),
):
    insight = await get_competitor_insight(company_id, db)
    if insight is None:
        return {
            "data": None,
            "error": None,
        }
    return {"data": insight, "error": None}


@router.get("/{company_id}/timeline")
async def signal_timeline(
    company_id: str,
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
):
    timeline = await get_signal_timeline(company_id, db, days=days)
    return {"data": timeline, "error": None}


@router.get("/{company_id}/alternatives")
async def alternative_companies(
    company_id: str,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_session),
):
    alternatives = await get_alternative_companies(company_id, db, limit=limit)
    return {"data": alternatives, "error": None}
