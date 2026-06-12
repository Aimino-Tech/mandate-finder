from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.database import AsyncSessionLocal
from mandate_finder.models.ab_testing import ABTest
from mandate_finder.services.ab_test_service import ABTestService
from src.workers.health import get_health, get_metrics, record_job, set_health, start_metrics_server

logger = logging.getLogger(__name__)

WORKER_NAME = "ab_test"
EVALUATION_INTERVAL_SECONDS = 300


async def evaluate_all_tests(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(ABTest).where(ABTest.status == "running")
    )
    tests = result.scalars().all()

    promoted = 0
    still_running = 0
    errors = 0

    for test in tests:
        service = ABTestService(db)
        try:
            outcome = await service.auto_promote(test.id)
            if outcome.get("promoted"):
                promoted += 1
                logger.info("Auto-promoted test %s: winner=%s p=%s",
                            test.id, outcome["winner_id"], outcome["best_p_value"])
            else:
                still_running += 1
        except Exception:
            logger.exception("Error evaluating test %s", test.id)
            errors += 1

    return {"promoted": promoted, "still_running": still_running, "errors": errors}


async def run_forever(interval: int = EVALUATION_INTERVAL_SECONDS) -> None:
    logger.info("A/B test worker started (interval=%ss)", interval)
    start_metrics_server(9092)
    set_health(WORKER_NAME, {"status": "ok", "interval_s": interval})

    while True:
        start = time.time()
        try:
            async with AsyncSessionLocal() as db:
                result = await evaluate_all_tests(db)
                logger.info("A/B test evaluation complete: %s", result)
            record_job(WORKER_NAME, time.time() - start, "ok")
        except Exception:
            logger.exception("A/B test worker cycle failed")
            record_job(WORKER_NAME, time.time() - start, "error")
        await asyncio.sleep(interval)


def main() -> None:
    asyncio.run(run_forever())
