from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, JobPosting
from src.pipeline.incremental_pipeline import IncrementalJobPipeline
from src.pipeline.pipeline_orchestrator import PipelineOrchestrator, PipelineRunResult, SourceConfig

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _make_job(i: int) -> dict[str, Any]:
    return {
        "id": f"src_{i}",
        "title": f"Software Engineer {i}",
        "company": f"Company{i % 50}",
        "location": "Berlin",
        "skills": ["Python", "FastAPI"],
        "posted_at": "2026-06-01T00:00:00",
        "source": "test",
    }


@pytest.mark.asyncio
async def test_pipeline_basic_ingest(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_basic",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
        batch_size=50,
    )
    records = [_make_job(i) for i in range(100)]
    await pipeline.write_batch(records)
    await pipeline.checkpoint()

    assert pipeline.state.total == 100
    assert pipeline.state.ingested == 100
    assert pipeline.state.skipped == 0
    assert len(pipeline.state.failed) == 0

    async with session_factory() as session:
        result = await session.execute(select(JobPosting))
        rows = result.scalars().all()
        assert len(rows) == 100


@pytest.mark.asyncio
async def test_pipeline_dedup(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_dedup",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )
    records = [_make_job(i) for i in range(50)]
    await pipeline.write_batch(records)
    await pipeline.checkpoint()

    records2 = [_make_job(i) for i in range(100)]
    await pipeline.write_batch(records2)
    await pipeline.checkpoint()

    assert pipeline.state.total == 100
    assert pipeline.state.ingested == 100
    assert pipeline.state.skipped == 50

    async with session_factory() as session:
        result = await session.execute(select(JobPosting))
        rows = result.scalars().all()
        assert len(rows) == 100


@pytest.mark.asyncio
async def test_pipeline_recovery(session_factory):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        state_path = f.name

    try:
        pipeline = IncrementalJobPipeline(
            source_name="test_recovery",
            session_factory=session_factory,
            state_dir=str(Path(state_path).parent),
            batch_size=100,
            checkpoint_interval=50,
        )
        pipeline.state_path = Path(state_path)

        records = [_make_job(i) for i in range(300)]

        await pipeline.write_batch(records[:150])
        await pipeline.checkpoint()

        pipeline2 = IncrementalJobPipeline(
            source_name="test_recovery",
            session_factory=session_factory,
            state_dir=str(Path(state_path).parent),
            batch_size=100,
            checkpoint_interval=50,
        )
        pipeline2.state_path = Path(state_path)
        pipeline2.recover()

        assert pipeline2.state.total == 150
        assert pipeline2.state.ingested == 150
        assert len(pipeline2.state.completed) == 150
        assert len(pipeline2.state.in_progress) == 0

        await pipeline2.write_batch(records[150:])
        await pipeline2.checkpoint()

        assert pipeline2.state.total == 300
        assert pipeline2.state.ingested == 300
        assert len(pipeline2.state.completed) == 300

        async with session_factory() as session:
            result = await session.execute(select(JobPosting))
            rows = result.scalars().all()
            assert len(rows) == 300

    finally:
        Path(state_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_pipeline_recovery_clean_start(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_clean",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )
    assert pipeline.recover() is False
    assert pipeline.state.total == 0


@pytest.mark.asyncio
async def test_pipeline_batch_flush(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_batch",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
        batch_size=20,
    )
    records = [_make_job(i) for i in range(55)]
    await pipeline.write_batch(records)
    assert len(pipeline._buffer) > 0
    await pipeline.flush()
    assert len(pipeline._buffer) == 0
    assert pipeline.state.ingested == 55


@pytest.mark.asyncio
async def test_orchestrator_run_source(session_factory):
    async def provider() -> list[list[dict[str, Any]]]:
        return [[_make_job(i) for i in range(25)], [_make_job(i) for i in range(25, 50)]]

    orchestrator = PipelineOrchestrator(
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )

    config = SourceConfig(
        name="test_orch",
        runner=lambda _: None,
        batch_size=100,
        checkpoint_interval=100,
    )

    result = await orchestrator.run_source(config, provider)
    assert isinstance(result, PipelineRunResult)
    assert result.total == 50
    assert result.ingested == 50
    assert result.error is None


@pytest.mark.asyncio
async def test_orchestrator_run_all_sources(session_factory):
    async def provider_a() -> list[list[dict[str, Any]]]:
        return [[_make_job(i) for i in range(10)]]

    async def provider_b() -> list[list[dict[str, Any]]]:
        return [[_make_job(i) for i in range(20)]]

    orchestrator = PipelineOrchestrator(
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )

    configs = [
        SourceConfig(name="source_a", runner=lambda _: None),
        SourceConfig(name="source_b", runner=lambda _: None),
    ]
    providers = {"source_a": provider_a, "source_b": provider_b}

    results = await orchestrator.run_all_sources(configs, providers)
    assert len(results) == 2
    assert results[0].ingested == 10
    assert results[1].ingested == 20


@pytest.mark.asyncio
async def test_pipeline_skip_empty_batch(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_empty",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )
    await pipeline.write_batch([])
    assert pipeline.state.total == 0
    await pipeline.flush()
    assert pipeline.state.total == 0


@pytest.mark.asyncio
async def test_pipeline_elapsed_time(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_elapsed",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )
    assert pipeline.elapsed == 0.0
    await pipeline.write_batch([_make_job(0)])
    await pipeline.checkpoint()
    assert pipeline.elapsed > 0.0


@pytest.mark.asyncio
async def test_pipeline_mark_cached(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_cached",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )
    pipeline.state.total = 10
    pipeline.state.in_progress = [f"src_{i}" for i in range(5)]
    pipeline.mark_cached([f"src_{i}" for i in range(3)])
    assert len(pipeline.state.cached) == 3
    assert len(pipeline.state.in_progress) == 2


@pytest.mark.asyncio
async def test_pipeline_mark_failed(session_factory):
    pipeline = IncrementalJobPipeline(
        source_name="test_failed",
        session_factory=session_factory,
        state_dir=tempfile.mkdtemp(),
    )
    pipeline.state.total = 10
    pipeline.state.in_progress = [f"src_{i}" for i in range(5)]
    pipeline.mark_failed([f"src_{i}" for i in range(2)])
    assert len(pipeline.state.failed) == 2
    assert len(pipeline.state.in_progress) == 3
