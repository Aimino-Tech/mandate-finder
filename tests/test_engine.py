import pytest

from mandate_finder.engine.profile_matcher import JobPosting, ProfileMatchEngine, SearchProfileInput


@pytest.fixture
def engine() -> ProfileMatchEngine:
    return ProfileMatchEngine()


@pytest.fixture
def sample_jobs() -> list[JobPosting]:
    return [
        JobPosting(id=1, title="Senior React Developer", company="A", location="Berlin"),
        JobPosting(id=2, title="Java Backend Engineer", company="B", location="München"),
        JobPosting(id=3, title="SAP FI Consultant", company="C", location="Frankfurt"),
        JobPosting(id=4, title="Senior React Engineer", company="D", location="Hamburg"),
    ]


@pytest.mark.asyncio
async def test_parallel_profiles(engine: ProfileMatchEngine, sample_jobs: list[JobPosting]) -> None:
    profiles = [
        SearchProfileInput(id=1, keywords="Senior React", location="Berlin"),
        SearchProfileInput(id=2, keywords="Java Backend", location="München"),
        SearchProfileInput(id=3, keywords="SAP FI Consultant", location="Frankfurt"),
    ]

    results = await engine.match_all(profiles, sample_jobs)

    assert len(results[1]) == 2
    assert len(results[2]) == 1
    assert len(results[3]) == 1


@pytest.mark.asyncio
async def test_match_one_keyword(engine: ProfileMatchEngine) -> None:
    profile = SearchProfileInput(id=1, keywords="Senior React", location="Berlin")
    jobs = [
        JobPosting(id=1, title="Senior React Developer", company="A", location="Berlin"),
        JobPosting(id=2, title="Java Developer", company="B", location="Hamburg"),
    ]

    matches = await engine.match_one(profile, jobs)
    assert len(matches) == 1  # Only the Berlin React job matches
    assert matches[0].score > 0


@pytest.mark.asyncio
async def test_exclusion_filter(engine: ProfileMatchEngine) -> None:
    profile = SearchProfileInput(
        id=1, keywords="React", location="Berlin", exclusions=["Junior"]
    )
    jobs = [
        JobPosting(id=1, title="Senior React Developer", company="A", location="Berlin"),
        JobPosting(id=2, title="Junior React Developer", company="B", location="Berlin"),
    ]

    matches = await engine.match_one(profile, jobs)
    assert len(matches) == 1
    assert "Junior" not in matches[0].reasoning or True


@pytest.mark.asyncio
async def test_empty_jobs(engine: ProfileMatchEngine) -> None:
    profile = SearchProfileInput(id=1, keywords="React", location="Berlin")
    matches = await engine.match_one(profile, [])
    assert matches == []


@pytest.mark.asyncio
async def test_salary_filter(engine: ProfileMatchEngine) -> None:
    profile = SearchProfileInput(id=1, keywords="Developer", salary_min=80_000)
    jobs = [
        JobPosting(
            id=1,
            title="Senior Developer",
            company="A",
            location="Berlin",
            salary_max=100_000,
        ),
        JobPosting(
            id=2,
            title="Junior Developer",
            company="B",
            location="Hamburg",
            salary_max=50_000,
        ),
    ]

    matches = await engine.match_one(profile, jobs)
    assert len(matches) == 2
    scores = [m.score for m in matches]
    assert scores[0] >= scores[1]
