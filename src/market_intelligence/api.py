from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response

from src.api.auth import get_current_user
from market_intelligence.models import EarlySignal, JobPosting
from market_intelligence.services.export import export_report
from market_intelligence.services.report_generator import generate_trend_report

router = APIRouter(prefix="/api/market-intelligence", tags=["market-intelligence"])


@router.get("/health")
async def health_check(_current_user: Any = Depends(get_current_user)) -> dict[str, Any]:
    return {"status": "ok", "service": "market-intelligence", "version": "0.1.0"}
_POSTINGS: list[JobPosting] = []
_SIGNALS: list[EarlySignal] = []


def get_postings() -> list[JobPosting]:
    return _POSTINGS


def get_signals() -> list[EarlySignal]:
    return _SIGNALS


PostingsDep = Annotated[list[JobPosting], Depends(get_postings)]
SignalsDep = Annotated[list[EarlySignal], Depends(get_signals)]


@router.post("/postings")
async def ingest_postings(postings: list[JobPosting], _current_user: Any = Depends(get_current_user)) -> dict[str, Any]:
    _POSTINGS.extend(postings)
    return {"ingested": len(postings), "total": len(_POSTINGS)}


@router.post("/signals")
async def ingest_signals(signals: list[EarlySignal], _current_user: Any = Depends(get_current_user)) -> dict[str, Any]:
    _SIGNALS.extend(signals)
    return {"ingested": len(signals), "total": len(_SIGNALS)}


@router.get("/trends")
async def get_trend_report(postings: PostingsDep, signals: SignalsDep, days: int = Query(90, ge=1, le=365), _user_filters: list[str] = Query(default=[]), _current_user: Any = Depends(get_current_user)) -> dict[str, Any]:
    from market_intelligence.services.trend_detector import compute_trend_series, top_growing_roles
    return {"top_growing_roles": top_growing_roles(postings, limit=10, days=days), "industry_pulse": compute_trend_series(postings, category_attr="industry", days=days), "early_warnings": [s for s in signals if s.confidence >= 0.3]}


@router.get("/trends/export")
async def export_trends_csv(postings: PostingsDep, signals: SignalsDep, days: int = Query(90, ge=1, le=365), fmt: str = Query("csv"), _current_user: Any = Depends(get_current_user)) -> Response:
    report = generate_trend_report(postings, signals, days=days)
    content = export_report(report, fmt=fmt)
    ds = datetime.now().date().isoformat()
    if fmt == "pdf":
        return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=trend-report-{ds}.pdf"})
    return PlainTextResponse(content=content.decode("utf-8"), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=trend-report-{ds}.csv"})


@router.get("/top-roles")
async def get_top_roles(postings: PostingsDep, days: int = Query(90, ge=1, le=365), limit: int = Query(10, ge=1, le=50), _current_user: Any = Depends(get_current_user)) -> dict[str, Any]:
    from market_intelligence.services.trend_detector import top_growing_roles
    return {"roles": top_growing_roles(postings, limit=limit, days=days)}


@router.get("/industry-pulse")
async def get_industry_pulse(postings: PostingsDep, days: int = Query(90, ge=1, le=365)) -> dict[str, Any]:
    from market_intelligence.services.trend_detector import compute_trend_series
    return {"industries": compute_trend_series(postings, category_attr="industry", days=days)}


@router.get("/early-warnings")
async def get_early_warnings(signals: SignalsDep, min_confidence: float = Query(0.3, ge=0, le=1)) -> dict[str, Any]:
    filtered = [s for s in signals if s.confidence >= min_confidence]
    return {"warnings": filtered, "total": len(filtered)}
