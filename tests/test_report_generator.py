from datetime import datetime, timedelta
from market_intelligence.models import EarlySignal, JobPosting, RoleCategory
from market_intelligence.services.report_generator import generate_trend_report, industry_pulse_summary


def _p(t, role=RoleCategory.engineering, da=0):
    return JobPosting(id=f"p{abs(hash(t+str(da)))}", title=t, company="T", role_category=role, posted_at=datetime.now() - timedelta(days=da))


def test_report():
    r = generate_trend_report([_p(f"R{i}", da=i % 30) for i in range(500)], days=60)
    assert len(r.top_growing_roles) <= 10 and r.generated_at is not None


def test_report_with_signals():
    s = EarlySignal(signal_type="funding", company="TC", headline="TC raises $10M", source_url="https://x.com", detected_at=datetime.now(), confidence=0.85)
    r = generate_trend_report([_p("E") for _ in range(10)], early_signals=[s])
    assert len(r.early_warnings) == 1 and r.early_warnings[0].company == "TC"


def test_pulse_summary():
    r = generate_trend_report([_p(f"P{i}", da=i % 60) for i in range(200)], days=90)
    assert "Industry Pulse" in industry_pulse_summary(r)
