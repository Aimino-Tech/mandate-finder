from datetime import datetime, timedelta
from market_intelligence.models import EarlySignal, Industry, JobPosting, RoleCategory
from market_intelligence.services.export import export_report
from market_intelligence.services.industry_classifier import classify_batch
from market_intelligence.services.report_generator import generate_trend_report
from market_intelligence.services.trend_detector import compute_trend_series, top_growing_roles
from market_intelligence.workers.early_signal_scraper import parse_signal


def _p(i, role=RoleCategory.engineering, ind=Industry.technology, da=0):
    return JobPosting(id=f"p{i}", title=f"{role.value} {i}", company=f"C{i%50}", role_category=role, industry=ind, skills=["py"] if role == RoleCategory.engineering else ["comm"], posted_at=datetime.now() - timedelta(days=da), source="t")


def test_10k():
    top = top_growing_roles([_p(i, da=i % 90) for i in range(10000)], limit=10, days=90, min_volume=10)
    assert len(top) <= 10


def test_signals():
    assert parse_signal("TC", "TC raises $10M Series B", "https://x.com").predicted_hiring_window_days == 45
    assert parse_signal("SA", "SA closes $5M Series A", "https://x.com/sa").predicted_hiring_window_days == 60
    assert parse_signal("UB", "UB lands $100M Series C", "https://x.com/sc").predicted_hiring_window_days == 30


def test_csv_columns():
    c = export_report(generate_trend_report([_p(i, da=i % 30) for i in range(200)], days=60), fmt="csv").decode()
    assert all(x in c for x in ["Category", "Date", "Growth Rate"])


def test_pct_change():
    s = compute_trend_series([_p(i, role=RoleCategory.engineering, da=1) for i in range(100)] + [_p(i + 1000, role=RoleCategory.engineering, da=89) for i in range(100)], days=90)
    e = [x for x in s if x.category == "engineering"]
    assert len(e) > 0 and e[0].growth_rate != 0.0


def test_classify_and_trend():
    c = classify_batch([_p(i, da=i % 60) for i in range(500)])
    assert all(p.industry is not None for p in c)
    assert len(generate_trend_report(c, days=90).top_growing_roles) > 0


def test_full_report():
    ps = [_p(i, da=i % 45) for i in range(500)]
    sigs = [EarlySignal(signal_type="funding", company="FGI", headline="FGI raises $50M", source_url="https://x.com", detected_at=datetime.now(), confidence=0.9)]
    r = generate_trend_report(ps, early_signals=sigs, days=90)
    assert len(r.early_warnings) == 1
    assert "FGI" in export_report(r, fmt="csv").decode()
