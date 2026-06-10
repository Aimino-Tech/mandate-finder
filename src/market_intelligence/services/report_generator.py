from datetime import datetime

from market_intelligence.models import EarlySignal, JobPosting, TrendReport
from market_intelligence.services.trend_detector import compute_trend_series, top_growing_roles


def generate_trend_report(postings: list[JobPosting], early_signals: list[EarlySignal] | None = None, *, user_filters: list[str] | None = None, days: int = 90) -> TrendReport:
    top_roles = top_growing_roles(postings, days=days, limit=10)
    industry_pulse = compute_trend_series(postings, category_attr="industry", days=days)
    industry_pulse.sort(key=lambda s: abs(s.growth_rate), reverse=True)
    user_insights: list[str] = []
    if user_filters:
        for filt in user_filters:
            for m in [r for r in top_roles if filt.lower() in r.category.lower()]:
                user_insights.append(f"{m.category.replace('_', ' ').title()} roles growing at {m.growth_rate * 100:.1f}% over {days} days")
    return TrendReport(generated_at=datetime.now(), top_growing_roles=top_roles, industry_pulse=industry_pulse, early_warnings=early_signals or [], user_insights=user_insights)


def industry_pulse_summary(report: TrendReport) -> str:
    lines = [f"# Industry Pulse \u2014 {report.generated_at.strftime('%B %Y')}\n"]
    for s in report.industry_pulse[:5]:
        emoji = "\U0001f7e2" if s.direction == "up" else "\U0001f534" if s.direction == "down" else "\u26aa"
        lines.append(f"{emoji} {s.category.title()}: {s.growth_rate * 100:+.1f}% ({s.direction})")
    return "\n".join(lines)


def early_warning_summary(signals: list[EarlySignal]) -> str:
    lines = ["## Early Warnings\n"]
    for s in signals:
        window = f" \u2192 predicted hiring in {s.predicted_hiring_window_days}d" if s.predicted_hiring_window_days else ""
        lines.append(f"  \u2022 {s.company}: {s.headline}{window}")
    return "\n".join(lines)
