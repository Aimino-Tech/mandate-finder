import hashlib
import hmac
import imaplib
import logging
import re
import time
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import parsedate_to_datetime

from src.config import settings
from src.database import SessionLocal
from src.models.ab_test import MessageEvent, MessageVariant

logger = logging.getLogger(__name__)


class ReplyDetector:
    def __init__(self, db_session=None):
        self.db = db_session or SessionLocal()
        self.imap = None

    def poll_imap(self) -> list[dict]:
        """Poll IMAP inbox for new replies and process them."""
        if not self._connect_imap():
            logger.warning("IMAP not configured, skipping poll")
            return []

        try:
            self.imap.select("INBOX")
            status, data = self.imap.search(None, "UNSEEN")
            if status != "OK":
                return []

            email_ids = data[0].split()
            replies = []

            for eid in email_ids:
                status, msg_data = self.imap.fetch(eid, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                reply = self._parse_email(raw_email)
                if reply:
                    processed = self.process_reply(reply)
                    replies.append(processed)

            return replies
        finally:
            self._disconnect_imap()

    def _connect_imap(self) -> bool:
        if not settings.imap_server or not settings.imap_user or not settings.imap_password:
            return False

        try:
            self.imap = imaplib.IMAP4_SSL(settings.imap_server)
            self.imap.login(settings.imap_user, settings.imap_password)
            return True
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return False

    def _disconnect_imap(self):
        if self.imap:
            try:
                self.imap.logout()
            except Exception:
                pass
            self.imap = None

    def _parse_email(self, raw_email: bytes) -> dict | None:
        msg = message_from_bytes(raw_email)
        subject = msg.get("Subject", "")
        sender = msg.get("From", "")
        message_id = msg.get("Message-ID", "")
        date_str = msg.get("Date", "")

        try:
            received_at = parsedate_to_datetime(date_str) if date_str else datetime.now(timezone.utc)
        except Exception:
            received_at = datetime.now(timezone.utc)

        body = self._get_email_body(msg)

        in_reply_to = msg.get("In-Reply-To", "")
        references = msg.get("References", "")

        return {
            "subject": subject,
            "sender": sender,
            "message_id": message_id,
            "received_at": received_at,
            "body": body,
            "in_reply_to": in_reply_to,
            "references": references,
        }

    def _get_email_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="ignore")
                elif part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="ignore")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="ignore")
        return ""

    def _extract_campaign_from_subject(self, subject: str) -> str | None:
        match = re.search(r're:?\s*\[([A-Z0-9_-]+)\]', subject, re.IGNORECASE)
        return match.group(1) if match else None

    def handle_sendgrid_webhook(self, payload: dict) -> dict:
        """Handle incoming SendGrid event webhook."""
        event_type = payload.get("event", "")
        if event_type != "reply":
            return {"handled": False, "reason": f"Ignored event type: {event_type}"}

        email = payload.get("email", "")
        campaign_id = payload.get("campaign_id", "")
        timestamp = payload.get("timestamp", time.time())

        variant = (
            self.db.query(MessageVariant)
            .filter(MessageVariant.campaign_id == campaign_id)
            .first()
        )

        if not variant:
            return {"handled": False, "reason": "No matching variant found"}

        event = MessageEvent(
            variant_id=variant.id,
            recipient=email,
            replied_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            metadata={"source": "sendgrid_webhook"},
        )
        self.db.add(event)
        self.db.commit()
        logger.info(f"Reply detected via SendGrid: {email} -> variant {variant.id}")
        return {"handled": True, "event_id": event.id, "latency_seconds": 0.0}

    def process_reply(self, reply: dict) -> dict:
        """Process a parsed reply: find matching variant and create event."""
        campaign_ref = self._extract_campaign_from_subject(reply.get("subject", ""))

        variant = None
        if campaign_ref:
            variant = (
                self.db.query(MessageVariant)
                .filter(MessageVariant.campaign_id == campaign_ref, MessageVariant.is_active.is_(True))
                .first()
            )

        if not variant:
            existing = (
                self.db.query(MessageEvent)
                .filter(
                    MessageEvent.recipient.ilike(f"%{self._extract_email(reply['sender'])}%"),
                    MessageEvent.replied_at.is_(None),
                )
                .first()
            )

            if existing:
                variant = existing.variant

        if not variant:
            variant = (
                self.db.query(MessageVariant)
                .filter(MessageVariant.is_active.is_(True))
                .first()
            )

        if not variant:
            logger.warning(f"No variant found for reply from {reply.get('sender')}")
            return {"handled": False, "reason": "No matching variant found"}

        event = MessageEvent(
            variant_id=variant.id,
            recipient=reply.get("sender", ""),
            replied_at=reply.get("received_at"),
            metadata={"source": "imap", "message_id": reply.get("message_id", "")},
        )
        self.db.add(event)
        self.db.commit()

        latency = (datetime.now(timezone.utc) - reply["received_at"]).total_seconds() if isinstance(reply.get("received_at"), datetime) else 0.0
        logger.info(f"Reply detected via IMAP: {reply.get('sender')} -> variant {variant.id} in {latency:.1f}s")
        return {"handled": True, "event_id": event.id, "latency_seconds": latency}

    def _extract_email(self, sender: str) -> str:
        match = re.search(r'<([^>]+)>', sender)
        return match.group(1) if match else sender
