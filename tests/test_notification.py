from datetime import datetime, timedelta

from market_intelligence.models import EarlySignal, JobPosting, TrendPoint, TrendReport, TrendSeries
from market_intelligence.services.notification import build_digest_email, generate_weekly_digests


def _p(i, da=0):
    return JobPosting(id=f"p{i}", title=f"Role {i}", company=f"C{i}", posted_at=datetime.now() - timedelta(days=da))


def test_build_email():
    r = TrendReport(generated_at=datetime.now(), top_growing_roles=[TrendSeries(category="eng", points=[TrendPoint(date=datetime.now().date(), value=10)], growth_rate=0.15, direction="up")], industry_pulse=[TrendSeries(category="tech", points=[TrendPoint(date=datetime.now().date(), value=5)], growth_rate=0.1, direction="up")], early_warnings=[EarlySignal(signal_type="funding", company="TC", headline="Raised", source_url="https://x.com", detected_at=datetime.now(), confidence=0.8)], user_insights=["Eng growing at 15%"])
    e = build_digest_email(r, user_email="a@x.com", user_name="A")
    assert e["to"] == "a@x.com" and "Eng" in e["html"] and "A" in e["text"]


def test_weekly():
    ps = [_p(i, da=i % 7) for i in range(50)]
    d = generate_weekly_digests([{"email": "a@x.com", "name": "A", "filters": []}], ps, days=7)
    assert len(d) == 1 and d[0]["to"] == "a@x.com"
