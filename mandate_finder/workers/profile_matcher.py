import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.db.session import async_session_factory
from mandate_finder.engine.profile_matcher import (
    JobPosting,
    ProfileMatchEngine,
    SearchProfileInput,
)
from mandate_finder.models.search_profile import SearchProfile
from mandate_finder.services.profile_notifier import ProfileNotifier


class ProfileMatchWorker:

    def __init__(self) -> None:
        self.engine = ProfileMatchEngine()
        self.notifier = ProfileNotifier()

    async def run_all_active(self) -> dict[uuid.UUID, int]:
        results: dict[uuid.UUID, int] = {}
        async with async_session_factory() as session:
            profiles = await self._get_active_profiles(session)
            for profile in profiles:
                count = await self.run_profile(profile.id, session)
                results[profile.id] = count
        return results

    async def run_profile(
        self,
        profile_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> int:
        if session is None:
            async with async_session_factory() as s:
                return await self._run_profile(profile_id, s)

        return await self._run_profile(profile_id, session)

    async def _run_profile(
        self,
        profile_id: uuid.UUID,
        session: AsyncSession,
    ) -> int:
        profile = await session.get(SearchProfile, profile_id)
        if profile is None or not profile.is_active:
            return 0

        profile_input = SearchProfileInput(
            id=profile.id,
            keywords=profile.keywords,
            location=profile.location,
            radius_km=profile.radius_km,
            industries=profile.industries.split(",") if profile.industries else None,
            salary_min=profile.salary_min,
            employment_type=profile.employment_type,
            exclusions=profile.exclusions.split(",") if profile.exclusions else None,
        )

        jobs = await self._fetch_new_jobs(session, profile_id)

        if not jobs:
            return 0

        matches = await self.engine.match_one(profile_input, jobs)

        for match in matches:
            session.add(match)

        profile.last_run_at = match.created_at

        await session.commit()

        await self.notifier.notify_new_matches(profile, matches)

        return len(matches)

    async def _get_active_profiles(
        self, session: AsyncSession
    ) -> list[SearchProfile]:
        result = await session.execute(
            select(SearchProfile).where(SearchProfile.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def _fetch_new_jobs(
        self,
        session: AsyncSession,
        profile_id: uuid.UUID,
    ) -> list[JobPosting]:
        profile = await session.get(SearchProfile, profile_id)
        if profile is None:
            return []

        keywords = [k.strip() for k in profile.keywords.split(",") if k.strip()]
        if not keywords:
            return []

        return [
            JobPosting(
                id=uuid.uuid4(),
                title=kw,
                company="placeholder",
                location=profile.location or "unknown",
            )
            for kw in keywords
        ]

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with async_session_factory() as session:
            yield session
