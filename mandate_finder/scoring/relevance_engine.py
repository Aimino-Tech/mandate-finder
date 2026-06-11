from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Protocol

from mandate_finder.scoring.explainer import generate_explanation
from mandate_finder.scoring.models import (
    JobPosting,
    MatchDimensions,
    MatchResult,
    SearchProfile,
    SuggestedAction,
)
from mandate_finder.scoring.scoring_weights import ScoringWeights

AGI_SCORING_PROMPT = """\
You are a lead-scoring AI for a headhunter. Given a search profile and a job posting, determine:
1. Relevance score (0-100) — how well this job matches the profile
2. Key matching dimensions — title, skills, location, industry, seniority
3. Explanation — concise reason for the score
4. Urgency — is this job recently posted? Likely hard to fill?
5. Suggested action — contact_immediately / add_to_watchlist / skip
"""


class AGIBackend(Protocol):
    async def score(self, profile: SearchProfile, job: JobPosting) -> MatchDimensions:
        ...


@dataclass
class LocalAGI:
    model_name: str = "default"

    async def score(self, profile: SearchProfile, job: JobPosting) -> MatchDimensions:
        return self._semantic_score(profile, job)

    def _semantic_score(self, profile: SearchProfile, job: JobPosting) -> MatchDimensions:
        profile_keywords_lower = profile.keywords.lower()
        title_lower = job.title.lower()
        desc_lower = job.description.lower()

        title_tokens = set(re.findall(r'\w+', title_lower))
        keyword_tokens = set(re.findall(r'\w+', profile_keywords_lower))
        desc_tokens = set(re.findall(r'\w+', desc_lower))

        title_overlap = len(title_tokens & keyword_tokens) / max(len(keyword_tokens), 1)
        desc_overlap = len(desc_tokens & keyword_tokens) / max(len(keyword_tokens), 1)

        title_match = min(1.0, title_overlap * 1.5)

        phrase_in_title = profile_keywords_lower in title_lower
        if phrase_in_title:
            title_match = max(title_match, 0.95)

        desc_phrase_match = profile_keywords_lower in desc_lower
        desc_context_score = min(1.0, desc_overlap * 1.5)
        if desc_phrase_match:
            desc_context_score = max(desc_context_score, 0.9)

        title_match = max(title_match, desc_context_score * 0.6)

        skills_match = 0.0
        if profile_keywords_lower and job.skills:
            profile_keywords_lower_set = set(re.findall(r'\w+', profile_keywords_lower))
            skill_matches = sum(
                1 for s in job.skills
                if any(
                    kw in s.lower() or s.lower() in kw
                    for kw in profile_keywords_lower_set
                )
            )
            skills_match = min(1.0, skill_matches / max(len(job.skills), 1) * 1.3)
            if skill_matches >= 2:
                skills_match = max(skills_match, 0.7)

        location_match = 0.0
        if profile.location and job.location:
            pl = profile.location.lower().strip()
            jl = job.location.lower().strip()
            if pl == jl:
                location_match = 1.0
            elif pl in jl or jl in pl:
                location_match = 0.85
            else:
                overlap = len(set(re.findall(r'\w+', pl)) & set(re.findall(r'\w+', jl)))
                location_match = min(1.0, overlap * 0.5)

        industry_match = 0.0
        if job.description and profile.industries:
            matches = sum(
                1 for ind in profile.industries
                if ind.lower() in desc_lower
            )
            industry_match = min(1.0, matches / max(len(profile.industries), 1))
            if matches > 0:
                industry_match = max(industry_match, 0.6)

        seniority_match = 0.5
        if job.seniority:
            js = job.seniority.lower()
            if profile.min_seniority:
                ps = profile.min_seniority.lower()
                if ps == js:
                    seniority_match = 1.0
                elif ps in js or js in ps:
                    seniority_match = 0.9
            seniority_levels = ["junior", "mid", "senior", "lead", "principal", "director"]
            if js in seniority_levels:
                profile_seniority = None
                if profile.min_seniority:
                    ps = profile.min_seniority.lower()
                    if ps in seniority_levels:
                        profile_seniority = ps
                if profile.keywords:
                    kw_words = title_tokens | set(re.findall(r'\w+', profile_keywords_lower))
                    kw_seniority = [w for w in kw_words if w in seniority_levels]
                    if kw_seniority:
                        profile_seniority = kw_seniority[0]
                if profile_seniority:
                    p_idx = seniority_levels.index(profile_seniority)
                    j_idx = seniority_levels.index(js)
                    diff = abs(p_idx - j_idx)
                    seniority_match = max(0.5, 1.0 - diff * 0.2)

        return MatchDimensions(
            title_match=round(title_match, 4),
            skills_match=round(skills_match, 4),
            location_match=round(location_match, 4),
            industry_match=round(industry_match, 4),
            seniority_match=round(seniority_match, 4),
        )


class RuleScorer:
    def score(self, profile: SearchProfile, job: JobPosting) -> MatchDimensions:
        title_match = self._title_keyword_match(profile.keywords, job.title)
        skills_match = self._skills_match(profile.keywords, job.skills)
        location_match = self._location_match(profile.location, job.location)
        industry_match = self._industry_match(profile.industries, job.description)
        seniority_match = self._seniority_match(profile.min_seniority, job.seniority)

        return MatchDimensions(
            title_match=round(title_match, 4),
            skills_match=round(skills_match, 4),
            location_match=round(location_match, 4),
            industry_match=round(industry_match, 4),
            seniority_match=round(seniority_match, 4),
        )

    def _title_keyword_match(self, keywords: str, title: str) -> float:
        kws = set(re.findall(r'\w+', keywords.lower()))
        title_tokens = set(re.findall(r'\w+', title.lower()))
        if not kws:
            return 0.0
        overlap = len(kws & title_tokens)
        return min(1.0, overlap / max(len(kws), 1) * 1.8)

    def _skills_match(self, keywords: str, skills: List[str]) -> float:
        if not skills:
            return 0.0
        kws = set(re.findall(r'\w+', keywords.lower()))
        if not kws:
            return 0.0
        matched = sum(
            1 for s in skills
            if any(kw in s.lower() or s.lower() in kw for kw in kws)
        )
        return min(1.0, matched / len(skills))

    def _location_match(self, profile_loc: Optional[str], job_loc: Optional[str]) -> float:
        if not profile_loc or not job_loc:
            return 0.0
        pl = profile_loc.lower().strip()
        jl = job_loc.lower().strip()
        if pl == jl:
            return 1.0
        if pl in jl or jl in pl:
            return 0.8
        return SequenceMatcher(None, pl, jl).ratio()

    def _industry_match(self, industries: List[str], description: str) -> float:
        if not industries or not description:
            return 0.0
        desc_lower = description.lower()
        matches = sum(1 for ind in industries if ind.lower() in desc_lower)
        return min(1.0, matches / max(len(industries), 1))

    def _seniority_match(self, min_seniority: Optional[str], seniority: Optional[str]) -> float:
        if not min_seniority or not seniority:
            return 0.5
        levels = ["junior", "mid", "senior", "lead", "principal", "director"]
        ps = min_seniority.lower()
        js = seniority.lower()
        if ps == js:
            return 1.0
        if ps in levels and js in levels:
            return max(0.0, 1.0 - abs(levels.index(ps) - levels.index(js)) * 0.25)
        return SequenceMatcher(None, ps, js).ratio()


class RelevanceEngine:
    def __init__(
        self,
        agi_backend: Optional[AGIBackend] = None,
        weights: Optional[ScoringWeights] = None,
    ):
        self._agi = agi_backend or LocalAGI()
        self._weights = weights or ScoringWeights()
        self._rule_scorer = RuleScorer()

    @property
    def weights(self) -> ScoringWeights:
        return self._weights

    async def score_job(self, profile: SearchProfile, job: JobPosting) -> MatchResult:
        rule_dims = self._rule_scorer.score(profile, job)
        agi_dims = await self._agi.score(profile, job)
        agi_dims = self._apply_feedback_adjustment(profile, agi_dims)

        rule_score = self._compute_dimension_score(rule_dims)
        agi_score = self._compute_dimension_score(agi_dims)
        fused_score = (
            self._weights.rule_weight * rule_score
            + self._weights.agi_weight * agi_score
        )

        merged_dims = self._merge_dimensions(rule_dims, agi_dims)
        fused_score = round(fused_score, 4)

        action = self._determine_action(fused_score, merged_dims)
        reasoning = generate_explanation(profile, job, MatchResult(
            score=fused_score,
            reasoning="",
            dimensions=merged_dims,
            suggested_action=action,
            rule_score=rule_score,
            agi_score=agi_score,
        ))

        return MatchResult(
            score=fused_score,
            reasoning=reasoning,
            dimensions=merged_dims,
            suggested_action=action,
            rule_score=round(rule_score, 4),
            agi_score=round(agi_score, 4),
        )

    def _apply_feedback_adjustment(
        self,
        profile: SearchProfile,
        dims: MatchDimensions,
    ) -> MatchDimensions:
        if not profile.user_feedback_history:
            return dims

        boost = 0.0
        penalize = 0.0
        for fb in profile.user_feedback_history:
            signal = fb.get("signal", "").lower()
            if signal == "relevant":
                boost += fb.get("weight", 0.1)
            elif signal == "not relevant":
                penalize += fb.get("weight", 0.1)

        net = min(boost, 0.3) - min(penalize, 0.3)
        return MatchDimensions(
            title_match=round(max(0.0, min(1.0, dims.title_match + net)), 4),
            skills_match=round(max(0.0, min(1.0, dims.skills_match + net)), 4),
            location_match=round(max(0.0, min(1.0, dims.location_match + net)), 4),
            industry_match=round(max(0.0, min(1.0, dims.industry_match + net)), 4),
            seniority_match=round(max(0.0, min(1.0, dims.seniority_match + net)), 4),
        )

    async def score_all(
        self,
        profile: SearchProfile,
        jobs: List[JobPosting],
    ) -> List[MatchResult]:
        results = []
        for job in jobs:
            result = await self.score_job(profile, job)
            results.append(result)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _compute_dimension_score(self, dims: MatchDimensions) -> float:
        score = 0.0
        for dim_name, dim_value in dims.as_dict().items():
            weight = self._weights.get_weight(dim_name)
            score += weight * dim_value
        return score

    def _merge_dimensions(self, rule: MatchDimensions, agi: MatchDimensions) -> MatchDimensions:
        rw = self._weights.rule_weight
        aw = self._weights.agi_weight
        return MatchDimensions(
            title_match=round(rw * rule.title_match + aw * agi.title_match, 4),
            skills_match=round(rw * rule.skills_match + aw * agi.skills_match, 4),
            location_match=round(rw * rule.location_match + aw * agi.location_match, 4),
            industry_match=round(rw * rule.industry_match + aw * agi.industry_match, 4),
            seniority_match=round(rw * rule.seniority_match + aw * agi.seniority_match, 4),
        )

    def _determine_action(
        self,
        score: float,
        dims: MatchDimensions,
    ) -> SuggestedAction:
        if score >= 0.7:
            return SuggestedAction.CONTACT_IMMEDIATELY
        if score >= 0.4:
            if dims.title_match > 0.5 or dims.skills_match > 0.5:
                return SuggestedAction.ADD_TO_WATCHLIST
            return SuggestedAction.SKIP
        return SuggestedAction.SKIP
