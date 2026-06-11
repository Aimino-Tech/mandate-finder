import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.db.session import get_session
from mandate_finder.models.profile_match import ProfileMatch
from mandate_finder.models.search_profile import SearchProfile
from mandate_finder.schemas.profile_match import FeedbackUpdate, ProfileMatchResponse
from mandate_finder.schemas.search_profile import (
    SearchProfileCreate,
    SearchProfileResponse,
    SearchProfileUpdate,
)
from mandate_finder.workers.profile_matcher import ProfileMatchWorker

router = APIRouter(prefix="/api/v1")


@router.post("/profiles", response_model=SearchProfileResponse, status_code=201)
async def create_profile(
    body: SearchProfileCreate,
    session: AsyncSession = Depends(get_session),
) -> SearchProfile:
    profile = SearchProfile(
        user_id=body.user_id,
        name=body.name,
        keywords=body.keywords,
        location=body.location,
        radius_km=body.radius_km,
        industries=",".join(body.industries) if body.industries else None,
        salary_min=body.salary_min,
        employment_type=body.employment_type,
        exclusions=",".join(body.exclusions) if body.exclusions else None,
        notify_on_score_above=body.notify_on_score_above,
        notify_channels=body.notify_channels,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


@router.get("/profiles", response_model=list[SearchProfileResponse])
async def list_profiles(
    user_id: uuid.UUID | None = Query(None),
    active_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> list[SearchProfile]:
    stmt = select(SearchProfile)
    if user_id is not None:
        stmt = stmt.where(SearchProfile.user_id == user_id)
    if active_only:
        stmt = stmt.where(SearchProfile.is_active.is_(True))
    stmt = stmt.order_by(SearchProfile.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/profiles/{profile_id}", response_model=SearchProfileResponse)
async def get_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SearchProfile:
    profile = await session.get(SearchProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/profiles/{profile_id}", response_model=SearchProfileResponse)
async def update_profile(
    profile_id: uuid.UUID,
    body: SearchProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> SearchProfile:
    profile = await session.get(SearchProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return profile

    if "industries" in update_data and isinstance(update_data["industries"], list):
        update_data["industries"] = ",".join(update_data["industries"])
    if "exclusions" in update_data and isinstance(update_data["exclusions"], list):
        update_data["exclusions"] = ",".join(update_data["exclusions"])

    stmt = (
        update(SearchProfile)
        .where(SearchProfile.id == profile_id)
        .values(**update_data)
        .returning(SearchProfile)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    profile = await session.get(SearchProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    await session.delete(profile)
    await session.commit()


@router.post("/profiles/{profile_id}/run", response_model=dict[str, int])
async def run_profile(
    profile_id: uuid.UUID,
) -> dict[str, int]:
    worker = ProfileMatchWorker()
    count = await worker.run_profile(profile_id)
    return {"matches_found": count}


@router.get("/profiles/{profile_id}/matches", response_model=list[ProfileMatchResponse])
async def list_matches(
    profile_id: uuid.UUID,
    min_score: float | None = Query(None),
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[ProfileMatch]:
    profile = await session.get(SearchProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    stmt = (
        select(ProfileMatch)
        .where(ProfileMatch.profile_id == profile_id)
        .order_by(ProfileMatch.score.desc())
        .limit(limit)
    )
    if min_score is not None:
        stmt = stmt.where(ProfileMatch.score >= min_score)

    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/matches/{match_id}/feedback", status_code=204)
async def submit_feedback(
    match_id: uuid.UUID,
    body: FeedbackUpdate,
    session: AsyncSession = Depends(get_session),
) -> None:
    match = await session.get(ProfileMatch, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    match.user_feedback = body.feedback
    await session.commit()
