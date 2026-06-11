from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.ab_test import Campaign, MessageEvent, MessageVariant
from src.workers.reply_detector import ReplyDetector


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def campaign(db_session):
    c = Campaign(name="test-campaign", industry="tech", role_seniority="senior", company_size="enterprise")
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture
def control_variant(db_session, campaign):
    v = MessageVariant(
        campaign_id=campaign.id, name="control", subject="Standard outreach",
        body="Hello, I wanted to reach out...", call_to_action="Schedule a call",
        personalization_level="low", channel="email", is_control=True,
    )
    db_session.add(v)
    db_session.commit()
    return v


class TestSendGridWebhook:
    def test_handles_reply_event(self, db_session, campaign, control_variant):
        detector = ReplyDetector(db_session)
        payload = {"event": "reply", "email": "user@test.com", "campaign_id": campaign.id,
                   "timestamp": datetime.utcnow().timestamp()}
        result = detector.handle_sendgrid_webhook(payload)
        assert result["handled"] is True
        assert "event_id" in result
        event = db_session.query(MessageEvent).filter(MessageEvent.id == result["event_id"]).first()
        assert event is not None
        assert event.recipient == "user@test.com"

    def test_ignores_non_reply_events(self, db_session):
        detector = ReplyDetector(db_session)
        payload = {"event": "open", "email": "user@test.com"}
        result = detector.handle_sendgrid_webhook(payload)
        assert result["handled"] is False
        assert "Ignored" in result["reason"]


class TestIMAPReplyDetection:
    def test_process_reply_maps_to_variant(self, db_session, control_variant):
        detector = ReplyDetector(db_session)
        reply = {"subject": "Re: [CAMPAIGN-123] Your outreach", "sender": "John Doe <john@acme.com>",
                 "message_id": "<msg-001>", "received_at": datetime.now(timezone.utc),
                 "body": "I'm interested, let's talk.", "in_reply_to": "", "references": ""}
        result = detector.process_reply(reply)
        assert result["handled"] is True
        assert "event_id" in result

    def test_reply_detection_latency_under_30s(self, db_session, control_variant):
        detector = ReplyDetector(db_session)
        reply = {"subject": "Re: Test outreach", "sender": "Jane <jane@corp.com>",
                 "message_id": "<msg-002>", "received_at": datetime.now(timezone.utc),
                 "body": "Let's do it.", "in_reply_to": "", "references": ""}
        result = detector.process_reply(reply)
        assert result["handled"] is True
        assert result["latency_seconds"] < 30

    def test_zero_replies_returns_insufficient_data(self, db_session):
        detector = ReplyDetector(db_session)
        reply = {"subject": "Re: [UNKNOWN] Something", "sender": "Unknown <unknown@test.com>",
                 "message_id": "<msg-003>", "received_at": datetime.now(timezone.utc),
                 "body": "Hello?", "in_reply_to": "", "references": ""}
        result = detector.process_reply(reply)
        assert result["handled"] is False
        assert "No matching variant found" in result["reason"]

    def test_imap_poll_returns_replies(self, db_session, control_variant):
        detector = ReplyDetector(db_session)
        detector._connect_imap = MagicMock(return_value=False)
        result = detector.poll_imap()
        assert result == []

    def test_parse_email_extracts_fields(self):
        detector = ReplyDetector(db_session=None)
        raw_email = (
            b"From: sender@test.com\r\nTo: recipient@test.com\r\n"
            b"Subject: Re: [CAMP-001] Outreach\r\nMessage-ID: <abc123>\r\n"
            b"Date: Tue, 10 Jun 2026 12:00:00 +0000\r\nIn-Reply-To: <orig-msg>\r\n\r\n"
            b"Thanks for reaching out!"
        )
        result = detector._parse_email(raw_email)
        assert result is not None
        assert result["sender"] == "sender@test.com"
        assert result["message_id"] == "<abc123>"

    def test_sendgrid_latency_is_zero(self, db_session, campaign, control_variant):
        detector = ReplyDetector(db_session)
        payload = {"event": "reply", "email": "ceo@acme.com", "campaign_id": campaign.id,
                   "timestamp": datetime.utcnow().timestamp()}
        result = detector.handle_sendgrid_webhook(payload)
        assert result["latency_seconds"] == 0.0
