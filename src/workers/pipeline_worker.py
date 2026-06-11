from __future__ import annotations

import logging

from taskiq import TaskiqState
from taskiq.events import TaskiqEvents
from taskiq_aio_pika import AioPikaBroker

from src.config import settings
from src.db.database import async_session_factory
from src.pipeline.pipeline_orchestrator import PipelineOrchestrator, SourceConfig

logger = logging.getLogger(__name__)


def _get_amqp_url() -> str:
    return getattr(settings, "taskiq_amqp_url", None) or "amqp://guest:guest@localhost:5672/"


broker = AioPikaBroker(_get_amqp_url())


async def _on_startup(state: TaskiqState) -> None:
    state.orchestrator = PipelineOrchestrator(
        session_factory=async_session_factory,
        state_dir="data/pipeline",
    )


broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _on_startup)


@broker.task(cron="0 6 * * *")
async def daily_pipeline_run() -> list[dict]:
    orchestrator = PipelineOrchestrator(
        session_factory=async_session_factory,
        state_dir="data/pipeline",
    )

    results = await orchestrator.run_all_sources(
        source_configs=_default_source_configs(),
        records_providers={},
    )
    return [r.__dict__ for r in results]


def _default_source_configs() -> list[SourceConfig]:
    return [
        SourceConfig(name="bundesagentur", runner=_stub_runner, batch_size=100, checkpoint_interval=100),
        SourceConfig(name="scraphermes", runner=_stub_runner, batch_size=50, checkpoint_interval=50),
        SourceConfig(name="schemaorg", runner=_stub_runner, batch_size=200, checkpoint_interval=200),
    ]


async def _stub_runner(pipeline) -> None:
    logger.info("Source runner for '%s' is not wired — no-op", pipeline.source_name)
