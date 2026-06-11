import logging
from datetime import UTC, datetime

import httpx

from mandate_finder.core.config import settings
from mandate_finder.models.profile_match import ProfileMatch
from mandate_finder.models.search_profile import SearchProfile

logger = logging.getLogger(__name__)


class ProfileNotifier:

    async def notify_new_matches(
        self,
        profile: SearchProfile,
        matches: list[ProfileMatch],
    ) -> None:
        high_score_matches = [
            m for m in matches if m.score >= profile.notify_on_score_above
        ]
        if not high_score_matches:
            return

        channels = [c.strip() for c in profile.notify_channels.split(",")]

        for match in high_score_matches:
            if "slack" in channels:
                await self._send_slack(profile, match)
            if "email" in channels:
                await self._send_email(profile, match)

            match.notified_at = datetime.now(UTC)
            match.is_new = False

    async def _send_slack(
        self,
        profile: SearchProfile,
        match: ProfileMatch,
    ) -> None:
        webhook = settings.slack_webhook_url
        if not webhook:
            logger.warning("No Slack webhook configured — skipping Slack notification")
            return

        payload = {
            "text": (
                f"🎯 *New high-relevance match for profile \"{profile.name}\"*\n"
                f"Score: *{match.score:.2f}*\n"
                f"Job Posting ID: `{match.job_posting_id}`\n"
                f"Reasoning: {match.reasoning or 'N/A'}"
            )
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook, json=payload, timeout=10)
                resp.raise_for_status()
                logger.info("Slack notification sent for match %s", match.id)
        except Exception as exc:
            logger.error("Failed to send Slack notification: %s", exc)

    async def _send_email(
        self,
        profile: SearchProfile,
        match: ProfileMatch,
    ) -> None:
        if not settings.smtp_host:
            logger.warning("No SMTP configured — skipping email notification")
            return

        logger.info(
            "Email notification for match %s (profile=%s, score=%.2f) — SMTP not fully implemented",
            match.id,
            profile.name,
            match.score,
        )
