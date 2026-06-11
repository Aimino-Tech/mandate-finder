from __future__ import annotations

from typing import Any, Dict, List

from mandate_finder.scoring.relevance_engine import MatchResult, SearchProfile


def generate_explanation(
    profile: SearchProfile,
    job: Dict[str, Any],
    results: List[MatchResult],
) -> str:
    """Generate a human-readable explanation of scoring results.

    Args:
        profile: The search profile used.
        job: The job that was scored (used for title/company display).
        results: One or more MatchResult instances (typically just one,
                 but the API can accept batch results).

    Returns:
        Multi-line human-readable string explaining the match.
    """
    if not results:
        return _no_match_explanation(profile, job)

    result = results[0] if len(results) == 1 else results[0]
    lines: List[str] = []
    job_title = job.get("title", "Unknown Position")
    company = job.get("company", "Unknown Company")

    lines.append(f"Job: {job_title} at {company}")
    lines.append(f"   Profile keywords: {profile.keywords}")
    if profile.location:
        lines.append(f"   Target location: {profile.location}")
    lines.append("")
    lines.append(f"Overall Score: {result.score:.2f} / 1.00")
    lines.append(f"   Urgency: {result.urgency.upper()}")
    lines.append(f"   Suggested Action: {result.suggested_action.value}")
    lines.append("")

    # Dimension breakdown
    lines.append("   Dimension Breakdown:")
    for dim, score in sorted(
        result.dimensions_breakdown.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        bar = _score_bar(score)
        lines.append(f"     - {dim.capitalize():12s}: {score:.2f} {bar}")

    lines.append("")
    lines.append("   Reasoning:")
    if result.reasoning:
        for line in result.reasoning.split("\n"):
            lines.append(f"     {line}")
    else:
        lines.append("     (no detailed reasoning available)")

    # Recommendations
    lines.append("")
    lines.append("   Action Guide:")
    action_guide = {
        "contact_immediately": "-> Contact this candidate/company as soon as possible.",
        "add_to_watchlist": "-> Add to watchlist for later review.",
        "skip": "-> Does not match your current criteria.",
    }
    lines.append(f"     {action_guide.get(result.suggested_action.value, '')}")

    if result.score >= 0.7:
        lines.append("")
        lines.append("   This is a strong match worth pursuing immediately.")

    return "\n".join(lines)


def _score_bar(score: float, width: int = 10) -> str:
    """Return a simple visual bar for a score."""
    filled = round(score * width)
    return "#" * filled + "-" * (width - filled)


def _no_match_explanation(profile: SearchProfile, job: Dict[str, Any]) -> str:
    """Return explanation when there are no results."""
    title = job.get("title", "Unknown Position")
    company = job.get("company", "Unknown Company")
    return (
        f"Job: {title} at {company}\n"
        f"   No scoring results available.\n"
        f"   The profile keywords '{profile.keywords}' did not produce any matches.\n"
        f"   Consider broadening your search criteria."
    )
