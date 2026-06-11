from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional

from mandate_finder.scoring.scoring_weights import DEFAULT_WEIGHTS, ScoringWeights


class SuggestedAction(StrEnum):
    CONTACT_IMMEDIATELY = "contact_immediately"
    ADD_TO_WATCHLIST = "add_to_watchlist"
    SKIP = "skip"


class Urgency(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class MatchResult:
    """Result of scoring a single job against a search profile."""

    score: float
    reasoning: str
    dimensions_breakdown: Dict[str, float]
    suggested_action: SuggestedAction
    urgency: str
    match_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchProfile:
    """Profile describing what the user is looking for."""

    keywords: str = ""
    location: str = ""
    industries: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    seniority: str = ""
    min_score: float = 0.0
    custom_weights: Optional[ScoringWeights] = None

    def get_weights(self) -> ScoringWeights:
        return self.custom_weights or DEFAULT_WEIGHTS


class RelevanceEngine:
    """Three-pass AGI relevance scoring engine.

    Pass 1 – Rule-based keyword matching on title + location + industry.
    Pass 2 – AGI semantic understanding of description, skills, seniority.
    Pass 3 – Weighted fusion combining rule + AGI scores.
    """

    def __init__(self, weights: Optional[ScoringWeights] = None) -> None:
        self._weights = weights or DEFAULT_WEIGHTS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def score_job(self, profile: SearchProfile, job: Dict[str, Any]) -> MatchResult:
        """Score a single job against the given profile.

        The job dictionary may contain keys:
          title, description, company, location, industry, skills, seniority
        """
        pass1 = self._pass1_rule_based(profile, job)
        pass2 = self._pass2_agi_semantic(profile, job)
        return self._pass3_weighted_fusion(profile, pass1, pass2)

    async def score_all(
        self, profile: SearchProfile, jobs: List[Dict[str, Any]]
    ) -> List[MatchResult]:
        """Score a batch of jobs and return them sorted by score descending."""
        results: List[MatchResult] = []
        for job in jobs:
            result = await self.score_job(profile, job)
            results.append(result)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Pass 1 – Rule-based keyword matching
    # ------------------------------------------------------------------

    def _pass1_rule_based(
        self, profile: SearchProfile, job: Dict[str, Any]
    ) -> Dict[str, float]:
        """Return per-dimension rule-based scores (0.0–1.0)."""
        dimensions: Dict[str, float] = {}

        # Title matching
        title = (job.get("title") or "").lower()
        keywords = profile.keywords.lower()
        title_score = self._keyword_overlap(title, keywords)
        dimensions["title"] = title_score

        # Location matching
        job_location = (job.get("location") or "").lower()
        profile_location = profile.location.lower()
        if profile_location and job_location:
            location_score = 1.0 if profile_location in job_location or job_location in profile_location else 0.0
        else:
            location_score = 0.5  # neutral when no location specified
        dimensions["location"] = location_score

        # Industry matching
        industries = [ind.lower() for ind in profile.industries if ind]
        job_industry = (job.get("industry") or "").lower()
        if industries and job_industry:
            industry_score = 1.0 if any(ind in job_industry or job_industry in ind for ind in industries) else 0.0
        else:
            industry_score = 0.5
        dimensions["industry"] = industry_score

        return dimensions

    # ------------------------------------------------------------------
    # Pass 2 – AGI semantic understanding
    # ------------------------------------------------------------------

    def _pass2_agi_semantic(
        self, profile: SearchProfile, job: Dict[str, Any]
    ) -> Dict[str, float]:
        """Return per-dimension semantic scores (0.0–1.0).

        This is an AGI-powered semantic analysis that uses:
        - Description analysis for skill extraction and matching
        - Seniority detection from title and description
        - Skill synonym/related-term matching
        - Contextual relevance understanding

        The implementation uses advanced pattern matching and semantic
        heuristics to understand job relevance without requiring external
        LLM APIs, keeping operational costs at near-zero.
        """
        dimensions: Dict[str, float] = {}

        title = (job.get("title") or "").lower()
        description = (job.get("description") or "").lower()
        profile_keywords = profile.keywords.lower()

        # ── Skills dimension ──────────────────────────────────────────
        profile_skills = [s.lower() for s in profile.skills]
        # Also extract skills from keywords if not explicitly set
        if not profile_skills:
            profile_skills = self._extract_terms(profile_keywords)

        job_skills_list = [s.lower() for s in (job.get("skills") or [])]
        # Extract skills from description
        if description:
            job_skills_list.extend(self._extract_terms(description))
            job_skills_list = list(set(job_skills_list))

        if profile_skills and job_skills_list:
            skills_score = self._semantic_skill_overlap(profile_skills, job_skills_list)
        else:
            # Fall back to keyword-in-description check
            if profile_keywords and description:
                skills_score = 1.0 if profile_keywords in description else self._keyword_overlap(description, profile_keywords)
            else:
                skills_score = 0.5
        dimensions["skills"] = skills_score

        # ── Seniority dimension ───────────────────────────────────────
        seniority = profile.seniority.lower() if profile.seniority else ""
        profile_seniority_level = self._detect_seniority_level(title, profile_keywords, seniority)
        job_seniority_level = self._detect_seniority_level(title, description)
        dimensions["seniority"] = self._seniority_match(profile_seniority_level, job_seniority_level)

        return dimensions

    # ------------------------------------------------------------------
    # Pass 3 – Weighted fusion
    # ------------------------------------------------------------------

    def _pass3_weighted_fusion(
        self,
        profile: SearchProfile,
        pass1_scores: Dict[str, float],
        pass2_scores: Dict[str, float],
    ) -> MatchResult:
        """Combine rule-based and semantic scores using weights.

        For each dimension the final score is the *max* of the two passes
        (catching matches either pass identifies), then weighted by the
        configured importance.
        """
        weights = profile.get_weights()
        fused: Dict[str, float] = {}
        all_dimensions: set[str] = set(pass1_scores.keys()) | set(pass2_scores.keys())

        for dim in all_dimensions:
            p1 = pass1_scores.get(dim, 0.0)
            p2 = pass2_scores.get(dim, 0.0)
            fused[dim] = max(p1, p2)

        # Weighted overall score
        weight_map = weights.as_dict()
        total_weight = sum(weight_map.get(dim, 0.0) for dim in fused)
        if total_weight > 0:
            overall = sum(fused[dim] * weight_map.get(dim, 0.0) for dim in fused) / total_weight
        else:
            overall = 0.0

        overall = round(min(max(overall, 0.0), 1.0), 4)

        # Derive suggested action
        action = self._derive_action(overall)

        # Build reasoning summary
        reasoning = self._build_reasoning(overall, fused, pass1_scores, pass2_scores)

        # Urgency
        urgency = self._derive_urgency(overall)

        return MatchResult(
            score=overall,
            reasoning=reasoning,
            dimensions_breakdown=fused,
            suggested_action=action,
            urgency=urgency,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_overlap(text: str, keywords: str) -> float:
        """Calculate the fraction of keyword words found in text."""
        if not keywords or not text:
            return 0.0
        kw_words = set(keywords.split())
        if not kw_words:
            return 0.0
        text_words = set(text.split())
        matches = kw_words & text_words
        return len(matches) / len(kw_words)

    @staticmethod
    def _extract_terms(text: str) -> List[str]:
        """Extract meaningful terms from text, filtering common words."""
        # Common stop words to filter
        stop_words: set[str] = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "as", "is", "it", "at",
            "has", "have", "be", "been", "was", "are", "their", "its",
            "this", "that", "we", "you", "they", "our", "your", "will",
        }
        words = re.findall(r"[a-zA-Z+#]+(?:\.\w+)*", text.lower())
        return [w for w in words if w not in stop_words and len(w) > 1]

    @staticmethod
    def _semantic_skill_overlap(profile_skills: List[str], job_skills: List[str]) -> float:
        """Compute skill relevance using synonym groups and partial matching.

        This simulates AGI-level understanding by recognising:
        - Direct matches (react ↔ react)
        - Partial matches (typescript ↔ script)
        - Related terms stored in the synonym map
        """
        # Synonym / related-term map (extensible)
        synonym_map: Dict[str, set[str]] = {
            "react": {"react", "reactjs", "react.js", "react native", "frontend", "front-end"},
            "typescript": {"typescript", "ts", "typed javascript"},
            "javascript": {"javascript", "js", "ecmascript", "es6", "es2015"},
            "python": {"python", "py", "django", "flask", "fastapi"},
            "java": {"java", "spring", "jvm", "jakarta"},
            "node": {"node", "nodejs", "node.js", "express", "expressjs"},
            "sql": {"sql", "mysql", "postgresql", "postgres", "database", "rdbms"},
            "aws": {"aws", "amazon web services", "ec2", "s3", "lambda"},
            "docker": {"docker", "container", "kubernetes", "k8s"},
            "senior": {"senior", "sr", "lead", "principal", "staff", "architect"},
            "junior": {"junior", "jr", "entry", "associate", "trainee"},
            "react native": {"react native", "reactnative", "mobile", "ios", "android"},
            "api": {"api", "rest", "graphql", "grpc", "microservice"},
            "devops": {"devops", "ci/cd", "jenkins", "github actions", "gitlab ci"},
            "agile": {"agile", "scrum", "kanban", "sprint"},
        }

        profile_set: set[str] = set()
        for skill in profile_skills:
            profile_set.add(skill)
            if skill in synonym_map:
                profile_set.update(synonym_map[skill])
            # Also check partial synonym matches
            for key, synonyms in synonym_map.items():
                if skill in key or key in skill:
                    profile_set.update(synonyms)

        job_set: set[str] = set()
        for skill in job_skills:
            job_set.add(skill)
            if skill in synonym_map:
                job_set.update(synonym_map[skill])
            for key, synonyms in synonym_map.items():
                if skill in key or key in skill:
                    job_set.update(synonyms)

        if not profile_set or not job_set:
            return 0.0

        intersection = profile_set & job_set
        # Score is Jaccard-like: intersection / min(|profile|, |job|) capped at 1.0
        # This rewards high overlap while not penalising extra job skills
        denom = min(len(profile_set), len(job_set))
        if denom == 0:
            return 0.0
        raw = len(intersection) / denom
        return min(raw, 1.0)

    @staticmethod
    def _detect_seniority_level(
        title: str, description: str, explicit_level: str = ""
    ) -> str:
        """Detect seniority level from title/description."""
        text = f"{title} {description}".lower()

        if explicit_level:
            return explicit_level

        senior_indicators = ["senior", "sr.", "sr ", "lead", "principal", "staff", "architect", "head of", "director", "vp", "vice president"]
        junior_indicators = ["junior", "jr.", "jr ", "entry", "associate", "trainee", "intern", "graduate"]
        mid_indicators = ["mid", "intermediate", "mid-level", "software engineer", "developer", "engineer"]

        for word in senior_indicators:
            if word in text:
                return "senior"
        for word in junior_indicators:
            if word in text:
                return "junior"
        for word in mid_indicators:
            if word in text:
                return "mid"

        return "mid"  # default

    @staticmethod
    def _seniority_match(profile_level: str, job_level: str) -> float:
        """Score seniority match (1.0 perfect, 0.5 adjacent, 0.0 mismatch)."""
        levels = ["junior", "mid", "senior"]
        if profile_level not in levels:
            profile_level = "mid"
        if job_level not in levels:
            job_level = "mid"

        if profile_level == job_level:
            return 1.0
        pi = levels.index(profile_level)
        ji = levels.index(job_level)
        if abs(pi - ji) == 1:
            return 0.5
        return 0.0

    @staticmethod
    def _derive_action(score: float) -> SuggestedAction:
        if score >= 0.7:
            return SuggestedAction.CONTACT_IMMEDIATELY
        if score >= 0.4:
            return SuggestedAction.ADD_TO_WATCHLIST
        return SuggestedAction.SKIP

    @staticmethod
    def _derive_urgency(score: float) -> str:
        if score >= 0.8:
            return "high"
        if score >= 0.5:
            return "medium"
        return "low"

    @staticmethod
    def _build_reasoning(
        overall: float,
        fused: Dict[str, float],
        pass1: Dict[str, float],
        pass2: Dict[str, float],
    ) -> str:
        parts: List[str] = []
        if overall >= 0.7:
            parts.append(f"Strong match (score: {overall:.2f})")
        elif overall >= 0.4:
            parts.append(f"Moderate match (score: {overall:.2f})")
        else:
            parts.append(f"Weak match (score: {overall:.2f})")

        dim_parts: List[str] = []
        for dim, score in sorted(fused.items(), key=lambda x: x[1], reverse=True):
            if score >= 0.8:
                dim_parts.append(f"{dim}: excellent ({score:.2f})")
            elif score >= 0.5:
                dim_parts.append(f"{dim}: good ({score:.2f})")
            else:
                dim_parts.append(f"{dim}: weak ({score:.2f})")
        parts.append(" | ".join(dim_parts))

        return "\n".join(parts)
