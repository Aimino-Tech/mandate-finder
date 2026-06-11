"""API routes for competitive intelligence insights with k-anonymity."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from mandate_finder.api.deps import CurrentUserId, DbSession
from mandate_finder.schemas.insights import (
    AlternativeRecommendation,
    CompanyInsightResponse,
    CompanySignalTimeline,
    HeatmapItem,
    HeatmapResponse,
    InsightReport,
    WatchlistCreate,
    WatchlistResponse,
)
from mandate_finder.services.competitor_insights import (
    add_to_watchlist,
    generate_report,
    get_alternative_recommendations,
    get_company_competition,
    get_company_signal,
    get_company_signal_timeline,
    get_heatmap,
    get_user_watchlist,
    remove_from_watchlist,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/company/{company_id}", response_model=CompanyInsightResponse)
async def get_company_insights(
    company_id: UUID,
    db: DbSession,
    _current_user_id: CurrentUserId,
) -> CompanyInsightResponse:
    """Get competition score and timeline for a company (k-anonymized)."""
    signal = await get_company_signal(db, company_id)
    if signal is None:
        competitor_count = await get_company_competition(db, company_id)
        return CompanyInsightResponse(
            company_id=company_id,
            company_name="Unknown",
            competitor_count=competitor_count,
            trend="stable",
            timeline=[],
        )

    timeline_signals = await get_company_signal_timeline(db, company_id, days=30)
    timeline = [
        CompanySignalTimeline(
            date=s.last_updated,
            competitor_count=s.competitor_count,
        )
        for s in timeline_signals
    ]

    return CompanyInsightResponse(
        company_id=signal.company_id,
        company_name=signal.company_name,
        competitor_count=signal.competitor_count,
        trend=signal.trend,
        timeline=timeline,
    )


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_insights_heatmap(
    db: DbSession,
    _current_user_id: CurrentUserId,
) -> HeatmapResponse:
    """Get all companies with activity levels (k-anonymized heatmap)."""
    items = await get_heatmap(db)
    return HeatmapResponse(
        items=[HeatmapItem(**item) for item in items],
    )


@router.get("/alternatives", response_model=list[AlternativeRecommendation])
async def get_alternatives(
    db: DbSession,
    _current_user_id: CurrentUserId,
    limit: int = Query(5, ge=1, le=20),
) -> list[AlternativeRecommendation]:
    """Get recommendations for companies with lower competition."""
    recommendations = await get_alternative_recommendations(db, limit=limit)
    return [AlternativeRecommendation(**r) for r in recommendations]


@router.post("/watchlist", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def add_company_to_watchlist(
    data: WatchlistCreate,
    db: DbSession,
    current_user_id: CurrentUserId,
) -> WatchlistResponse:
    """Add a company to the user's watchlist."""
    entry = await add_to_watchlist(
        db,
        user_id=current_user_id,
        company_id=data.company_id,
        company_name=data.company_name,
        notify_on_change=data.notify_on_change,
    )
    return WatchlistResponse(
        id=entry.id,
        company_id=entry.company_id,
        company_name=entry.company_name,
        notify_on_change=entry.notify_on_change,
        created_at=entry.created_at,
    )


@router.delete("/watchlist/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_company_from_watchlist(
    watchlist_id: UUID,
    db: DbSession,
    current_user_id: CurrentUserId,
) -> None:
    """Remove a company from the user's watchlist."""
    deleted = await remove_from_watchlist(db, current_user_id, watchlist_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist entry not found.",
        )


@router.get("/watchlist", response_model=list[WatchlistResponse])
async def list_watchlist(
    db: DbSession,
    current_user_id: CurrentUserId,
) -> list[WatchlistResponse]:
    """List all watchlist entries for the current user."""
    entries = await get_user_watchlist(db, current_user_id)
    return [
        WatchlistResponse(
            id=e.id,
            company_id=e.company_id,
            company_name=e.company_name,
            notify_on_change=e.notify_on_change,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/report", response_model=InsightReport)
async def get_insight_report(
    db: DbSession,
    current_user_id: CurrentUserId,
) -> InsightReport:
    """Generate a full insight report with signals, watchlist, and alternatives."""
    report_data = await generate_report(db, current_user_id)
    return InsightReport(**report_data)
