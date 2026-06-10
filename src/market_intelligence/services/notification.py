from market_intelligence.models import EarlySignal, JobPosting, TrendReport
from market_intelligence.services.report_generator import generate_trend_report

_UP = "\U0001f7e2"
_DOWN = "\U0001f534"


def build_digest_email(report: TrendReport, user_email: str = "user@example.com", user_name: str = "User") -> dict[str, str]:
    top_html = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #eee;'>{s.category.replace('_', ' ').title()}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center;'>{_UP if s.direction == 'up' else _DOWN}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;'>{s.growth_rate * 100:+.1f}%</td></tr>"
        for s in report.top_growing_roles[:5]
    )
    warn_html = "".join(
        f"<li><b>{s.company}</b>: {s.headline}{' (hiring in ~' + str(s.predicted_hiring_window_days) + 'd)' if s.predicted_hiring_window_days else ''}</li>"
        for s in report.early_warnings[:3]
    )
    pulse_html = "".join(f"<li><b>{s.category.title()}</b>: {s.growth_rate * 100:+.1f}% ({s.direction})</li>" for s in report.industry_pulse[:5])
    insights = "".join(f"<li>{i}</li>" for i in report.user_insights)
    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;">
<div style="max-width:600px;margin:auto;background:white;border-radius:8px;overflow:hidden;">
<div style="background:#2b5797;color:white;padding:20px;text-align:center;">
<h1 style="margin:0;font-size:20px;">Market Intelligence Digest</h1>
<p style="margin:5px 0 0;opacity:.9;">{report.generated_at.strftime('%A, %B %d, %Y')}</p></div>
<div style="padding:20px;"><p>Hello {user_name},</p><p>Here is your weekly market intelligence summary.</p>
{insights and f'<h3>Your Insights</h3><ul>{insights}</ul>' or ''}
<h3>Top Growing Roles</h3><table style="width:100%;border-collapse:collapse;">
<tr style="background:#f8f9fa;"><th style="padding:8px;text-align:left;">Role</th><th style="padding:8px;">Trend</th><th style="padding:8px;text-align:right;">Growth</th></tr>
{top_html}</table>
<h3>Industry Pulse</h3><ul>{pulse_html}</ul>
{warn_html and f'<h3>Early Warnings</h3><ul>{warn_html}</ul>' or ''}
<p style="margin-top:20px;font-size:12px;color:#888;">Generated automatically.</p></div></div></body></html>"""
    text = ("Market Intelligence Digest\n\nHello " + user_name + ",\n\nTop Growing Roles:\n"
            + "\n".join(f"  {s.category.replace('_', ' ').title()}: {s.growth_rate * 100:+.1f}% ({s.direction})" for s in report.top_growing_roles[:5])
            + "\n\nIndustry Pulse:\n"
            + "\n".join(f"  {s.category.title()}: {s.growth_rate * 100:+.1f}%" for s in report.industry_pulse[:5])
            + "\n\nEarly Warnings:\n"
            + ("\n".join(f"  {s.company}: {s.headline}" for s in report.early_warnings[:3]) if report.early_warnings else "  None")
            + "\n\nGenerated automatically.")
    return {"to": user_email, "subject": f"Market Intelligence Digest \u2014 {report.generated_at.strftime('%Y-%m-%d')}", "html": html, "text": text}


def generate_weekly_digests(users: list[dict[str, object]], postings: list[JobPosting], signals: list[EarlySignal] | None = None, days: int = 7) -> list[dict[str, str]]:
    digests: list[dict[str, str]] = []
    for user in users:
        raw = user.get("filters", [])
        uf: list[str] = raw if isinstance(raw, list) else []
        fr = generate_trend_report(postings, signals or [], user_filters=uf, days=days)
        email_val = user.get("email", "user@example.com")
        name_val = user.get("name", "User")
        digests.append(build_digest_email(fr, user_email=str(email_val) if not isinstance(email_val, str) else email_val, user_name=str(name_val) if not isinstance(name_val, str) else name_val))
    return digests
