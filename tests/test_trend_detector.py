from datetime import datetime, timedelta

from market_intelligence.models import JobPosting, RoleCategory
from market_intelligence.services.trend_detector import compute_trend_series, top_growing_roles


def _p(title, role=RoleCategory.engineering, da=0):
    return JobPosting(id=f"p{abs(hash(title+str(da)))}", title=title, company="T", role_category=role, posted_at=datetime.now() - timedelta(days=da))


def test_empty():
    assert compute_trend_series([], days=30) == []


def test_single_role():
    s = compute_trend_series([_p("E", role=RoleCategory.engineering, da=i) for i in range(30)], days=60)
    assert len([x for x in s if x.category == "engineering"]) > 0


def test_top_sorted():
    ps = [_p(f"E{i}", role=RoleCategory.engineering, da=i) for i in range(90)] + [_p(f"S{i}", role=RoleCategory.sales, da=i) for i in range(90)]
    top = top_growing_roles(ps, limit=3)
    assert len(top) <= 3
    for i in range(len(top) - 1):
        assert top[i].growth_rate >= top[i + 1].growth_rate


def test_stable():
    s = compute_trend_series([_p("E", role=RoleCategory.engineering, da=i % 3) for i in range(90)], days=90)
    for x in s:
        if x.category == "engineering":
            assert x.direction == "stable"
            return
