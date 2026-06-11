"""Periodic A/B test worker.

Computes statistics for all running A/B tests and auto-promotes
winning variants when p < significance_threshold.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.database import AsyncSessionLocal
from mandate_finder.models.ab_testing import ABTest
from mandate_finder.services.ab_test_service import ABTestService

logger = logging.getLogger(__name__)

EVALUATION_INTERVAL_SECONDS = 300  # 5 minutes


async def evaluate_all_tests(db: AsyncSession) -> dict[str, int]:
    """Evaluate all running A/B tests and auto-promote where appropriate."""
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
    """Run the evaluation loop continuously."""
    logger.info("A/B test worker started (interval=%ss)", interval)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await evaluate_all_tests(db)
                logger.info("A/B test evaluation complete: %s", result)
        except Exception:
            logger.exception("A/B test worker cycle failed")
        await asyncio.sleep(interval)


def main() -> None:
    """Entry point for CLI / taskiq."""
    asyncio.run(run_forever())
