"""Reply Detection worker.

Polls IMAP for email replies and processes webhook callbacks.
Pauses campaigns when a human reply is detected.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.database import AsyncSessionLocal
from mandate_finder.services.reply_detector import IMAPReplyDetector

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30  # must be <= 30s per spec


async def poll_all_campaigns(db: AsyncSession, imap_config: dict | None = None) -> int:
    """Poll IMAP for all active campaigns that have A/B tests running."""
    from mandate_finder.models.ab_testing import ABTest

    result = await db.execute(
        select(ABTest).where(ABTest.status == "running")
    )
    running_tests = result.scalars().all()

    total_events = 0
    for test in running_tests:
        detector = IMAPReplyDetector(
            db=db,
            campaign_id=test.campaign_id,
            **(imap_config or {}),
        )
        try:
            events = await detector.poll_once()
            total_events += len(events)
            for event in events:
                logger.info("Reply detected: campaign=%s channel=%s event=%s",
                            event.campaign_id, event.channel, event.id)
        except Exception:
            logger.exception("Error polling campaign %s", test.campaign_id)

    return total_events


async def run_forever(interval: int = POLL_INTERVAL_SECONDS,
                      imap_config: dict | None = None) -> None:
    """Run the reply detection loop continuously."""
    logger.info("Reply detection worker started (interval=%ss)", interval)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                count = await poll_all_campaigns(db, imap_config)
                if count:
                    logger.info("Detected %d new replies this cycle", count)
        except Exception:
            logger.exception("Reply detection cycle failed")
        await asyncio.sleep(interval)


def main() -> None:
    """Entry point for CLI / taskiq."""
    asyncio.run(run_forever())
