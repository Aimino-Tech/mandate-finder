from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.pipeline.incremental_pipeline import IncrementalJobPipeline
from src.services.admin_metrics import record_metric

logger = logging.getLogger(__name__)

SourceRunner = Callable[[IncrementalJobPipeline], Awaitable[None]]


@dataclass
class SourceConfig:
    name: str
    runner: SourceRunner
    batch_size: int = 100
    checkpoint_interval: int = 100


@dataclass
class PipelineRunResult:
    source: str
    total: int = 0
    ingested: int = 0
    skipped: int = 0
    failed: int = 0
    elapsed: float = 0.0
    error: str | None = None


class PipelineOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        state_dir: str = "data/pipeline",
    ) -> None:
        self.session_factory = session_factory
        self.state_dir = state_dir
        self._shutdown_event = asyncio.Event()
        self._active_pipelines: list[IncrementalJobPipeline] = []
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._trigger_shutdown)

    def _trigger_shutdown(self) -> None:
        logger.warning("Shutdown signal received — checkpointing active pipelines")
        self._shutdown_event.set()

    async def run_source(
        self,
        config: SourceConfig,
        records_provider: Callable[[], Awaitable[list[list[dict[str, Any]]]]],
    ) -> PipelineRunResult:
        pipeline = IncrementalJobPipeline(
            source_name=config.name,
            session_factory=self.session_factory,
            state_dir=self.state_dir,
            batch_size=config.batch_size,
            checkpoint_interval=config.checkpoint_interval,
        )
        self._active_pipelines.append(pipeline)
        pipeline.recover()

        result = PipelineRunResult(source=config.name)

        try:
            async for batch in self._batches(records_provider):
                if self._shutdown_event.is_set():
                    logger.info("Shutdown requested — finishing current batch")
                    break
                await pipeline.write_batch(batch)

            await pipeline.checkpoint()

            result.total = pipeline.state.total
            result.ingested = pipeline.state.ingested
            result.skipped = pipeline.state.skipped
            result.failed = len(pipeline.state.failed)
            result.elapsed = pipeline.elapsed

            await self._record_metrics(result)

            logger.info(
                "Pipeline %s done — total=%d ingested=%d skipped=%d failed=%d elapsed=%.2fs",
                config.name,
                result.total,
                result.ingested,
                result.skipped,
                result.failed,
                result.elapsed,
            )

        except Exception as exc:
            await pipeline.checkpoint()
            result.error = str(exc)
            logger.exception("Pipeline %s failed", config.name)

        finally:
            self._active_pipelines.remove(pipeline)

        return result

    async def _record_metrics(self, result: PipelineRunResult) -> None:
        try:
            async with self.session_factory() as session:
                await record_metric(session, "jobs_ingested", float(result.ingested), source=result.source)
                await record_metric(session, "jobs_skipped", float(result.skipped), source=result.source)
                await record_metric(session, "jobs_failed", float(result.failed), source=result.source)
                await record_metric(session, "pipeline_duration_seconds", result.elapsed, source=result.source)
        except Exception:
            logger.exception("Failed to record pipeline metrics for %s", result.source)

    async def _batches(
        self,
        records_provider: Callable[[], Awaitable[list[list[dict[str, Any]]]]],
    ) -> Any:
        batches = await records_provider()
        for batch in batches:
            yield batch

    async def run_all_sources(
        self,
        source_configs: list[SourceConfig],
        records_providers: dict[str, Callable[[], Awaitable[list[list[dict[str, Any]]]]]],
    ) -> list[PipelineRunResult]:
        results: list[PipelineRunResult] = []
        for config in source_configs:
            provider = records_providers.get(config.name)
            if provider is None:
                logger.warning("No records provider for source '%s' — skipping", config.name)
                continue
            result = await self.run_source(config, provider)
            results.append(result)
        return results
