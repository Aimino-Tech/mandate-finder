import uuid
from dataclasses import dataclass

from mandate_finder.models.profile_match import ProfileMatch


@dataclass
class JobPosting:
    id: uuid.UUID | str
    title: str
    company: str
    location: str
    description: str = ""
    industries: list[str] | None = None
    salary_max: float | None = None
    employment_type: str | None = None


@dataclass
class SearchProfileInput:
    id: uuid.UUID | int | str
    keywords: str
    location: str | None = None
    radius_km: int | None = None
    industries: list[str] | None = None
    salary_min: float | None = None
    employment_type: str | None = None
    exclusions: list[str] | None = None


class ProfileMatchEngine:

    def __init__(self) -> None:
        self._cache: dict[str, float] = {}

    async def match_all(
        self,
        profiles: list[SearchProfileInput],
        jobs: list[JobPosting],
    ) -> dict[int | str | uuid.UUID, list[ProfileMatch]]:
        results: dict[int | str | uuid.UUID, list[ProfileMatch]] = {}
        for profile in profiles:
            matches = await self.match_one(profile, jobs)
            results[profile.id] = matches
        return results

    async def match_one(
        self,
        profile: SearchProfileInput,
        jobs: list[JobPosting],
    ) -> list[ProfileMatch]:
        keyword_tokens = self._tokenize(profile.keywords)
        location_tokens = self._tokenize(profile.location or "")
        exclusion_tokens = self._tokenize(" ".join(profile.exclusions or []))
        industry_set = set(i.lower() for i in (profile.industries or []))

        matches: list[ProfileMatch] = []
        for job in jobs:
            score = self._compute_score(
                job=job,
                keyword_tokens=keyword_tokens,
                location_tokens=location_tokens,
                exclusion_tokens=exclusion_tokens,
                industry_set=industry_set,
                profile=profile,
            )
            if score > 0:
                pid = profile.id
                if isinstance(pid, str) and len(pid) == 36:
                    pid = uuid.UUID(pid)
                jid = job.id
                if isinstance(jid, str) and len(jid) == 36:
                    jid = uuid.UUID(jid)
                matches.append(
                    ProfileMatch(
                        id=uuid.uuid4(),
                        profile_id=pid,
                        job_posting_id=jid,
                        score=score,
                        reasoning=self._build_reasoning(
                            job, keyword_tokens, location_tokens
                        ),
                    )
                )

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def _compute_score(
        self,
        job: JobPosting,
        keyword_tokens: set[str],
        location_tokens: set[str],
        exclusion_tokens: set[str],
        industry_set: set[str],
        profile: SearchProfileInput,
    ) -> float:
        score = 0.0
        title_lower = job.title.lower()
        desc_lower = job.description.lower()
        company_lower = job.company.lower()
        combined_text = f"{title_lower} {desc_lower} {company_lower}"

        for kw in keyword_tokens:
            if kw in combined_text:
                score += 0.15
        score = min(score, 0.6)

        for ex in exclusion_tokens:
            if ex in combined_text:
                return 0.0

        for lt in location_tokens:
            if lt in job.location.lower():
                score += 0.2
                break

        if industry_set and job.industries:
            if industry_set & set(i.lower() for i in job.industries):
                score += 0.1

        if profile.salary_min and job.salary_max:
            if job.salary_max >= profile.salary_min:
                score += 0.1

        if profile.employment_type and job.employment_type:
            if profile.employment_type.lower() == job.employment_type.lower():
                score += 0.1

        return round(min(score, 1.0), 2)

    def _build_reasoning(
        self,
        job: JobPosting,
        keyword_tokens: set[str],
        location_tokens: set[str],
    ) -> str:
        matched_keywords = [kw for kw in keyword_tokens if kw in job.title.lower()]
        matched_location = any(lt in job.location.lower() for lt in location_tokens)
        parts = []
        if matched_keywords:
            parts.append(f"keywords: {', '.join(matched_keywords)}")
        if matched_location:
            parts.append("location matched")
        return "; ".join(parts) if parts else "general match"

    def _tokenize(self, text: str) -> set[str]:
        return set(w.lower().strip(".,!?;:()[]") for w in text.split() if w.strip())
