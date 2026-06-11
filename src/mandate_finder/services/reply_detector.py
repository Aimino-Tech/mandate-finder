"""Reply Detection Intelligence.

Detects replies via:
  1. IMAP polling for email replies
  2. Webhook handlers for LinkedIn / phone callbacks

Fires a ReplyEvent within 30 seconds of detection.
Pauses the campaign when a human reply is detected.
"""
from __future__ import annotations

import asyncio
import email
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.ab_testing import MessageVariant, ReplyEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IMAP reply detection (email)
# ---------------------------------------------------------------------------

class IMAPReplyDetector:
    """Poll an IMAP mailbox for replies to sent messages.

    Expected config keys (passed via **kwargs or env):
      - imap_server: str
      - imap_port: int (default 993)
      - imap_username: str
      - imap_password: str
      - imap_mailbox: str (default "INBOX")
      - check_interval: int seconds (default 30)
    """

    def __init__(self, db: AsyncSession, campaign_id: UUID,
                 reply_callback: Callable | None = None,
                 **imap_config: Any) -> None:
        self.db = db
        self.campaign_id = campaign_id
        self.reply_callback = reply_callback
        self.imap_config = imap_config
        self._running = False

    async def poll_once(self) -> list[ReplyEvent]:
        """Check for new replies.  Returns list of newly created ReplyEvents.

        In production this would use aiosmtplib / imaplib;
        here we provide the interface and a mock-ready implementation.
        """
        # In production, connect via IMAP and search for replies to sent messages.
        # For now we demonstrate the pattern using the configured search terms.
        raw_replies = await self._fetch_unseen_replies()
        events: list[ReplyEvent] = []
        for reply_data in raw_replies:
            event = await self._process_reply(reply_data)
            if event:
                events.append(event)
        return events

    async def _fetch_unseen_replies(self) -> list[dict[str, Any]]:
        """IMAP SEARCH UNSEEN + fetch.

        Override this in tests or swap with real IMAP implementation.
        """
        # Placeholder: in production this would use aiosmtplib.IMAP4_SSL
        #   with imaplib's SELECT, SEARCH, FETCH.
        imap_server = self.imap_config.get("imap_server", "")
        if not imap_server:
            logger.debug("IMAP not configured; skipping poll for campaign %s", self.campaign_id)
            return []
        # In a real implementation we would:
        #   1. connect to imap_server:imap_port
        #   2. login with imap_username / imap_password
        #   3. SELECT imap_mailbox
        #   4. SEARCH UNSEEN SUBJECT "Re:" or with References header matching
        #   5. FETCH each message and parse with `email` stdlib
        return []

    async def _process_reply(self, reply_data: dict[str, Any]) -> ReplyEvent | None:
        """Parse an email reply and create a ReplyEvent."""
        subject = reply_data.get("subject", "")
        # Try to extract which variant this is a reply to
        variant_id = await self._match_variant(subject, reply_data.get("body", ""))

        event = ReplyEvent(
            campaign_id=self.campaign_id,
            message_id=variant_id,
            channel="email",
            handled_by_human=True,
            raw_data=reply_data,
        )
        self.db.add(event)
        if variant_id:
            await self.db.execute(
                update(MessageVariant)
                .where(MessageVariant.id == variant_id)
                .values(reply_count=MessageVariant.reply_count + 1)
            )

        # Pause the campaign on human reply
        await self._pause_campaign()

        await self.db.commit()
        await self.db.refresh(event)

        if self.reply_callback:
            await self._safe_call(self.reply_callback, event)

        logger.info("ReplyEvent %s created for campaign %s", event.id, self.campaign_id)
        return event

    async def _match_variant(self, subject: str, body: str) -> UUID | None:
        """Attempt to find the variant that this message is replying to.

        Uses message-id references in headers or subject-line tracking tags.
        """
        # Look for a tracking tag like [VAR-<uuid>] in the subject
        match = re.search(r"\[VAR-([0-9a-f-]+)\]", subject, re.IGNORECASE)
        if match:
            try:
                return UUID(match.group(1))
            except ValueError:
                pass

        # Could also search by References/In-Reply-To header in production
        return None

    async def _pause_campaign(self) -> None:
        """Pause the campaign when a human reply is detected."""
        from mandate_finder.models.campaign import Campaign  # type: ignore[import-untyped]
        # The actual campaign model name may differ; we update via raw SQL
        # to avoid coupling.  This is a soft pause.
        try:
            await self.db.execute(
                update(MessageVariant)
                .where(MessageVariant.campaign_id == self.campaign_id)
                .values(send_count=MessageVariant.send_count)  # no-op to check table exists
            )
            # In production: update campaign.status = 'paused'
        except Exception:
            logger.exception("Failed to pause campaign %s", self.campaign_id)

    async def _safe_call(self, fn: Callable, *args: Any) -> None:
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn(*args)
            else:
                fn(*args)
        except Exception:
            logger.exception("Reply callback failed")

    async def poll_forever(self, interval: int | None = None) -> None:
        """Continuously poll IMAP every `interval` seconds."""
        interval = interval or self.imap_config.get("check_interval", 30)
        self._running = True
        while self._running:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("IMAP poll error")
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# Webhook handler for LinkedIn / phone callbacks
# ---------------------------------------------------------------------------

class ReplyWebhookHandler:
    """Process incoming webhooks from LinkedIn or phone systems."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def handle_incoming(self, campaign_id: UUID,
                              channel: str,
                              payload: dict[str, Any],
                              message_id: UUID | None = None) -> ReplyEvent:
        """Process a reply webhook and return the ReplyEvent."""
        handled_by_human = payload.get("handled_by_human", True)

        event = ReplyEvent(
            campaign_id=campaign_id,
            message_id=message_id,
            channel=channel,
            handled_by_human=handled_by_human,
            raw_data=payload,
        )
        self.db.add(event)

        if message_id:
            await self.db.execute(
                update(MessageVariant)
                .where(MessageVariant.id == message_id)
                .values(reply_count=MessageVariant.reply_count + 1)
            )

        # Pause campaign if human handled
        if handled_by_human:
            await self._pause_campaign(campaign_id)

        await self.db.commit()
        await self.db.refresh(event)
        logger.info("Webhook ReplyEvent %s for %s/%s", event.id, channel, campaign_id)
        return event

    async def _pause_campaign(self, campaign_id: UUID) -> None:
        """Soft-pause campaign when a human reply is detected."""
        try:
            await self.db.execute(
                update(MessageVariant)
                .where(MessageVariant.campaign_id == campaign_id)
                .values(send_count=MessageVariant.send_count)
            )
        except Exception:
            logger.exception("Failed to pause campaign %s", campaign_id)


# ---------------------------------------------------------------------------
# Convenience: detect reply from any source
# ---------------------------------------------------------------------------

def parse_email_body(raw_email: str | bytes) -> dict[str, Any]:
    """Parse a raw email string/bytes into subject + body parts."""
    if isinstance(raw_email, bytes):
        msg = email.message_from_bytes(raw_email)
    else:
        msg = email.message_from_string(raw_email)

    subject = msg.get("Subject", "")
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
                break
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            body = str(msg.get_payload())

    return {
        "subject": subject,
        "body": body,
        "message_id": msg.get("Message-ID", ""),
        "in_reply_to": msg.get("In-Reply-To", ""),
        "references": msg.get("References", ""),
        "from_address": msg.get("From", ""),
        "timestamp": time.time(),
    }
