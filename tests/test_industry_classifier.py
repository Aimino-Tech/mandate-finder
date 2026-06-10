from datetime import datetime
from market_intelligence.models import Industry, JobPosting, RoleCategory
from market_intelligence.services.industry_classifier import classify_job_posting


def _p(title, skills=None):
    return JobPosting(id=f"t{abs(hash(title))}", title=title, company="T", skills=skills or [], posted_at=datetime.now())


def test_health():
    assert classify_job_posting(_p("Oberarzt im Krankenhaus")).industry == Industry.health


def test_tech():
    assert classify_job_posting(_p("Senior Software Engineer")).industry == Industry.technology


def test_finance():
    assert classify_job_posting(_p("Investment Banker")).industry == Industry.finance


def test_role_eng():
    assert classify_job_posting(_p("Senior Backend Developer")).role_category == RoleCategory.engineering


def test_role_sales():
    assert classify_job_posting(_p("Account Executive B2B")).role_category == RoleCategory.sales


def test_fallback():
    p = classify_job_posting(_p("xyzzy unknown"))
    assert p.industry == Industry.other and p.role_category == RoleCategory.other
