from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from src.pipeline.pipeline_orchestrator import SourceConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/status")
async def pipeline_status() -> dict[str, Any]:
    return {
        "status": "idle",
        "available_sources": [s.name for s in _default_source_configs()],
    }


async def _stub_runner(pipeline) -> None:
    logger.info("Source runner for '%s' is not wired — no-op", pipeline.source_name)


def _default_source_configs() -> list[SourceConfig]:
    return [
        SourceConfig(name="bundesagentur", runner=_stub_runner, batch_size=100, checkpoint_interval=100),
        SourceConfig(name="scraphermes", runner=_stub_runner, batch_size=50, checkpoint_interval=50),
        SourceConfig(name="schemaorg", runner=_stub_runner, batch_size=200, checkpoint_interval=200),
    ]
