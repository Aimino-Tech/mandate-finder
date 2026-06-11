from __future__ import annotations

from typing import List

from mandate_finder.scoring.models import JobPosting, MatchResult, SearchProfile


def generate_explanation(
    profile: SearchProfile,
    job: JobPosting,
    match: MatchResult,
) -> str:
    matched_on: List[str] = []
    dims = match.dimensions
    threshold = 0.3

    if dims.title_match >= threshold:
        matched_on.append("title")
    if dims.skills_match >= threshold:
        matched_on.append("skills")
    if dims.location_match >= threshold:
        matched_on.append("location")
    if dims.industry_match >= threshold:
        matched_on.append("industry")
    if dims.seniority_match >= threshold:
        matched_on.append("seniority")

    parts: List[str] = []
    if matched_on:
        parts.append(f"Matched on: {', '.join(matched_on)}")

    if dims.title_match > 0.5:
        parts.append(f"Job title '{job.title}' aligns with your search for '{profile.keywords}'")
    if dims.skills_match > 0.5 and job.skills:
        parts.append(f"Required skills ({', '.join(job.skills[:3])}) match your expertise")
    if dims.location_match > 0.5 and job.location:
        parts.append(f"Location {job.location} matches your target area")
    if dims.industry_match > 0.5 and profile.industries:
        parts.append("Industry matches your target sectors")
    if dims.seniority_match > 0.5 and job.seniority:
        parts.append(f"Seniority level '{job.seniority}' is appropriate")

    if not parts:
        parts.append("Limited alignment with search criteria")

    parts.append(f"Overall confidence: {match.score:.0%}")

    return " | ".join(parts)


def format_confidence_breakdown(match: MatchResult) -> dict:
    dims = match.dimensions.as_dict()
    return {
        "dimensions": dims,
        "rule_score": match.rule_score,
        "agi_score": match.agi_score,
        "fused_score": match.score,
    }


def generate_short_reason(job: JobPosting, match: MatchResult) -> str:
    dims = match.dimensions
    top_dims = sorted(
        dims.as_dict().items(),
        key=lambda x: x[1],
        reverse=True,
    )[:2]

    reasons = []
    for name, score in top_dims:
        label = name.replace("_match", "").capitalize()
        if score > 0.6:
            reasons.append(f"strong {label} match ({score:.0%})")
        elif score > 0.3:
            reasons.append(f"moderate {label} match ({score:.0%})")

    if reasons:
        return f"{job.title} at {job.company}: {' and '.join(reasons)}"
    return f"{job.title} at {job.company}: low relevance ({match.score:.0%})"
