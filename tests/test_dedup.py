import pytest

from mandate_finder.scrapers.job_dedup import JobDedupEngine


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (
            {"title": "Senior React Developer", "company": "Company A", "location": "Berlin"},
            {"title": "Sr. React Dev", "company": "Company A", "location": "Berlin"},
            "FINGERPRINT",
        ),
        (
            {"title": "Senior React Developer", "company": "Company A", "location": "Berlin"},
            {"title": "Senior Frontend Engineer", "company": "Company A", "location": "Berlin"},
            "SEMANTIC",
        ),
        (
            {"title": "Senior React Developer", "company": "Company A", "location": "Berlin"},
            {"title": "Java Backend Developer", "company": "Company B", "location": "München"},
            "NEW",
        ),
    ],
)
async def test_dedup_levels(a, b, expected):
    dedup = JobDedupEngine()
    decision, _, confidence = await dedup.check_new(a, existing=[b])
    assert decision == expected
    if expected == "FINGERPRINT":
        assert confidence > 0.95


class TestSourceIdDedup:
    async def test_exact_source_id_match(self):
        dedup = JobDedupEngine()
        job = {"source": "linkedin", "source_job_id": "123", "title": "Engineer", "company": "Acme", "location": "Berlin"}
        existing = [{"source": "linkedin", "source_job_id": "123", "title": "Engineer", "company": "Acme", "location": "Berlin"}]
        decision, _, confidence = await dedup.check_new(job, existing=existing)
        assert decision == "EXISTING"
        assert confidence > 0.95

    async def test_no_source_id_falls_through(self):
        dedup = JobDedupEngine()
        job = {"title": "Engineer", "company": "Acme", "location": "Berlin"}
        existing = [{"source": "linkedin", "source_job_id": "123", "title": "Engineer", "company": "Acme", "location": "Berlin"}]
        decision, _, _ = await dedup.check_new(job, existing=existing)
        assert decision != "EXISTING"

    async def test_different_source_ids_are_unique(self):
        dedup = JobDedupEngine()
        job = {"source": "linkedin", "source_job_id": "123", "title": "Engineer", "company": "Acme", "location": "Berlin"}
        existing = [{"source": "stepstone", "source_job_id": "456", "title": "Engineer", "company": "Acme", "location": "Berlin"}]
        decision, _, _ = await dedup.check_new(job, existing=existing)
        assert decision != "EXISTING"


class TestCacheDedup:
    async def test_cache_hit_returns_early(self):
        dedup = JobDedupEngine()
        job = {"source": "linkedin", "source_job_id": "123", "title": "Engineer", "company": "Acme", "location": "Berlin"}
        cache = {"source:linkedin:123": "EXISTING"}
        decision, _, confidence = await dedup.check_new(job, cache=cache)
        assert decision == "EXISTING"
        assert confidence == 1.0

    async def test_cache_miss_falls_through(self):
        dedup = JobDedupEngine()
        job = {"source": "linkedin", "source_job_id": "123", "title": "Engineer", "company": "Acme", "location": "Berlin"}
        cache = {"source:stepstone:789": "EXISTING"}
        decision, _, _ = await dedup.check_new(job, cache=cache)
        assert decision != "EXISTING"


class TestSemanticDedup:
    async def test_semantic_merge(self):
        dedup = JobDedupEngine()
        job = {"title": "Senior Python Developer", "company": "Company A", "location": "Berlin"}
        existing = [{"title": "Sr. Python Software Engineer", "company": "Company A", "location": "Berlin"}]
        decision, _, confidence = await dedup.check_new(job, existing=existing)
        assert decision == "MERGED"
        assert confidence >= 0.55

    async def test_same_company_same_location_fuzzy_title(self):
        dedup = JobDedupEngine()
        job = {"title": "Frontend Developer (React)", "company": "TechCorp", "location": "Munich"}
        existing = [{"title": "React Frontend Engineer", "company": "TechCorp", "location": "Munich"}]
        decision, _, confidence = await dedup.check_new(job, existing=existing)
        assert decision == "MERGED"
        assert confidence >= 0.55

    async def test_different_companies_not_semantic_match(self):
        dedup = JobDedupEngine()
        job = {"title": "Senior React Developer", "company": "Company A", "location": "Berlin"}
        existing = [{"title": "Senior React Developer", "company": "Company B", "location": "Berlin"}]
        decision, _, _ = await dedup.check_new(job, existing=existing)
        assert decision == "MERGED"


class TestNormalizer:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Sr. Full Stack Eng. (m/f/x)", "Senior Full Stack Engineer"),
            ("JR Software Developer", "Junior Software Developer"),
            ("VP of Engineering", "Vice President of Engineering"),
            ("Senior React Developer", "Senior React Developer"),
            ("Frontend Eng.", "Frontend Engineer"),
        ],
    )
    async def test_normalize_title(self, raw, expected):
        from mandate_finder.scrapers.job_normalizer import JobNormalizer

        normalizer = JobNormalizer()
        result = await normalizer.normalize_title(raw)
        assert result == expected

    @pytest.mark.parametrize(
        "text,expected_min,expected_max,expected_currency",
        [
            ("€50,000 - €70,000 per year", 50000, 70000, "EUR"),
            ("$80k - $120k", 80000, 120000, "USD"),
            ("£40,000 - £55,000", 40000, 55000, "GBP"),
        ],
    )
    async def test_extract_salary(self, text, expected_min, expected_max, expected_currency):
        from mandate_finder.scrapers.job_normalizer import JobNormalizer

        normalizer = JobNormalizer()
        job = {"salary": text}
        salary = await normalizer._extract_salary(job, text)
        assert salary["min"] == expected_min
        assert salary["max"] == expected_max
        assert salary["currency"] == expected_currency

    @pytest.mark.parametrize(
        "field_value,expected",
        [
            ("full-time", "full_time"),
            ("part-time", "part_time"),
            ("contract", "contract"),
            ("freelance", "freelance"),
        ],
    )
    async def test_extract_employment_type_from_field(self, field_value, expected):
        from mandate_finder.scrapers.job_normalizer import JobNormalizer

        normalizer = JobNormalizer()
        result = await normalizer._extract_employment_type(
            {"employment_type": field_value}, ""
        )
        assert result == expected

    async def test_extract_skills_from_description(self):
        from mandate_finder.scrapers.job_normalizer import JobNormalizer

        normalizer = JobNormalizer()
        desc = "We are looking for a Python developer with experience in Django, PostgreSQL, and AWS. Knowledge of Docker and Kubernetes is a plus."
        skills = await normalizer.extract_skills(desc)
        assert "Python" in skills
        assert "Django" in skills
        assert "PostgreSQL" in skills
        assert "AWS" in skills
        assert "Docker" in skills
        assert "Kubernetes" in skills

    async def test_full_normalize(self):
        from mandate_finder.scrapers.job_normalizer import JobNormalizer

        normalizer = JobNormalizer()
        raw = {
            "title": "Sr. Python Engineer (m/f/x)",
            "company": "TechCorp",
            "location": "Berlin, Germany",
            "description": "Build APIs with FastAPI and PostgreSQL. Salary: €80,000 - €100,000.",
            "salary": "€80,000 - €100,000 per year",
            "employment_type": "full-time",
        }
        result = await normalizer.normalize(raw)
        assert result.title == "Senior Python Engineer"
        assert result.company == "TechCorp"
        assert result.salary_min == 80000
        assert result.salary_max == 100000
        assert result.salary_currency == "EUR"
        assert result.employment_type == "full_time"
        assert "FastAPI" in result.skills
        assert "PostgreSQL" in result.skills
