from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.compliance.consent_manager import ConsentManager
from src.compliance.data_governance import DataGovernance, DataType
from src.compliance.deletion_manager import DeletionManager
from src.compliance.encryption import (
    PII_FIELDS,
    decrypt_field,
    encrypt_field,
    is_pii_field,
    mask_field,
    rotate_encryption_key,
)


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "user@example.com"
        encrypted = encrypt_field(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_field(encrypted)
        assert decrypted == plaintext

    def test_encrypt_decrypt_empty_string(self):
        assert encrypt_field("") == ""
        assert decrypt_field("") == ""

    def test_encrypt_phone_number(self):
        phone = "+491234567890"
        encrypted = encrypt_field(phone)
        decrypted = decrypt_field(encrypted)
        assert decrypted == phone

    def test_encrypt_special_characters(self):
        text = "Müller Straße 123! @#$%^&*()"
        encrypted = encrypt_field(text)
        decrypted = decrypt_field(encrypted)
        assert decrypted == text

    def test_mask_field(self):
        assert mask_field("user@example.com", visible_chars=2) == "us" + "*" * 14
        assert mask_field("ab", visible_chars=2) == "ab"
        assert mask_field("", visible_chars=2) == ""

    def test_mask_field_default_visible(self):
        expected = "te" + "*" * (len("test@example.com") - 2)
        assert mask_field("test@example.com") == expected

    def test_is_pii_field(self):
        assert is_pii_field("email") is True
        assert is_pii_field("phone") is True
        assert is_pii_field("name") is True
        assert is_pii_field("not_pii") is False

    def test_pii_fields_set(self):
        assert "email" in PII_FIELDS
        assert "linkedin_url" in PII_FIELDS


class TestDataGovernance:
    def test_default_policies_exist(self):
        gov = DataGovernance()
        assert len(gov.policies) == 6

    def test_contact_retention_24_months(self):
        gov = DataGovernance()
        policy = gov.get_policy(DataType.CONTACT)
        assert policy.ttl_days == 730
        assert policy.action == "anonymize"

    def test_log_retention(self):
        gov = DataGovernance()
        policy = gov.get_policy(DataType.LOG)
        assert policy.ttl_days == 365

    def test_is_expired(self):
        gov = DataGovernance()
        assert gov.is_expired(DataType.CONTACT, datetime.now(UTC) - timedelta(days=1)) is False
        assert gov.is_expired(DataType.CONTACT, datetime.now(UTC) - timedelta(days=800)) is True
        assert gov.is_expired(DataType.CONTACT, None) is False

    async def test_log_retention_action(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            gov = DataGovernance()
            log = await gov.log_retention_action(session, DataType.CONTACT, "r1", "anonymize", reason="test")
            assert log.id is not None
            assert log.data_type == "contact"

    async def test_get_retention_logs(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            gov = DataGovernance()
            await gov.log_retention_action(session, DataType.CONTACT, "r1", "anonymize")
            logs = await gov.get_retention_logs(session)
            assert len(logs) >= 1


class TestConsentManager:
    async def test_record_consent(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            record = await manager.record_consent(user_id="u1", purpose="data_processing", ip_address="127.0.0.1")
            assert record.id is not None
            assert record.purpose == "data_processing"

    async def test_record_consent_invalid_purpose(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            with pytest.raises(ValueError):
                await manager.record_consent(user_id="u1", purpose="invalid", ip_address="127.0.0.1")

    async def test_has_valid_consent(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            await manager.record_consent(user_id="u1", purpose="data_processing", ip_address="127.0.0.1")
            assert await manager.has_valid_consent("u1", "data_processing") is True
            assert await manager.has_valid_consent("u1", "marketing") is False

    async def test_revoke_consent(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            await manager.record_consent(user_id="u1", purpose="data_processing", ip_address="127.0.0.1")
            assert await manager.revoke_consent("u1", "data_processing") is True
            assert await manager.has_valid_consent("u1", "data_processing") is False

    async def test_register_opt_out(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            opt_out = await manager.register_opt_out(company_domain="example.com", company_name="Example GmbH")
            assert opt_out.company_domain == "example.com"
            assert opt_out.is_active is True

    async def test_duplicate_opt_out(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            await manager.register_opt_out(company_domain="example.com")
            with pytest.raises(ValueError):
                await manager.register_opt_out(company_domain="example.com")

    async def test_is_opted_out(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            assert await manager.is_opted_out("example.com") is False
            await manager.register_opt_out(company_domain="example.com")
            assert await manager.is_opted_out("example.com") is True

    async def test_list_opt_outs(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            await manager.register_opt_out(company_domain="example.com")
            await manager.register_opt_out(company_domain="test.de")
            opt_outs = await manager.list_opt_outs()
            assert len(opt_outs) >= 2

    def test_uwg_compliance(self):
        result = ConsentManager.check_uwg_compliance("example.com", opted_out=True)
        assert result["compliant"] is False
        assert "not permitted" in result["message"]
        result = ConsentManager.check_uwg_compliance("example.com", opted_out=False)
        assert result["compliant"] is True


class TestDeletionManager:
    async def test_create_deletion_request(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = DeletionManager(session)
            request = await manager.create_deletion_request(user_id="u1", reason="test")
            assert request.id is not None
            assert request.status == "pending"

    async def test_get_pending_requests(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = DeletionManager(session)
            await manager.create_deletion_request(user_id="u1")
            pending = await manager.get_pending_requests()
            assert len(pending) >= 1

    async def test_get_deletion_status(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = DeletionManager(session)
            await manager.create_deletion_request(user_id="u1")
            status = await manager.get_deletion_status("u1")
            assert len(status) >= 1
            assert status[0]["user_id"] == "u1"

    async def test_export_user_data(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            manager = DeletionManager(session)
            export = await manager.export_user_data("u1")
            assert export["user_id"] == "u1"
            assert "exported_at" in export


@pytest.fixture
async def seed_api_key(test_session_factory: async_sessionmaker):
    from src.core.security import hash_api_key
    from src.db.models import APIKey
    key_hash = hash_api_key("test-compliance-key-123")
    async with test_session_factory() as session:
        session.add(APIKey(key_hash=key_hash, name="Compliance Test Key", scopes=["*"], tier="professional"))
        await session.commit()


@pytest.fixture
async def auth_headers():
    return {"Authorization": "Bearer test-compliance-key-123"}


class TestComplianceAPI:
    async def test_retention_policies_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/retention-policies")
        assert resp.status_code == 200
        data = resp.json()
        assert "policies" in data
        assert "contact" in data["policies"]

    async def test_record_consent_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/compliance/consent", json={"user_id": "api-user", "purpose": "data_processing", "ip_address": "127.0.0.1", "user_agent": "pytest"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["purpose"] == "data_processing"

    async def test_record_consent_invalid_purpose(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/compliance/consent", json={"user_id": "u1", "purpose": "invalid", "ip_address": "127.0.0.1"}, headers=auth_headers)
        assert resp.status_code == 400

    async def test_revoke_consent_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        await client.post("/api/v1/compliance/consent", json={"user_id": "rev-user", "purpose": "marketing", "ip_address": "127.0.0.1"}, headers=auth_headers)
        resp = await client.post("/api/v1/compliance/consent/rev-user/revoke/marketing", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"

    async def test_register_opt_out_endpoint(self, client: AsyncClient):
        resp = await client.post("/api/v1/compliance/opt-out", json={"company_domain": "optout-test.de", "company_name": "OptOut GmbH"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    async def test_duplicate_opt_out_endpoint(self, client: AsyncClient):
        await client.post("/api/v1/compliance/opt-out", json={"company_domain": "dup-test.de"})
        resp = await client.post("/api/v1/compliance/opt-out", json={"company_domain": "dup-test.de"})
        assert resp.status_code == 400

    async def test_check_opt_out_endpoint(self, client: AsyncClient):
        await client.post("/api/v1/compliance/opt-out", json={"company_domain": "check-optout.de"})
        resp = await client.get("/api/v1/compliance/opt-out/check-optout.de")
        assert resp.status_code == 200
        assert resp.json()["opted_out"] is True

    async def test_check_uwg_endpoint(self, client: AsyncClient):
        resp = await client.post("/api/v1/compliance/check-uwg", json={"company_domain": "uwg-test.de"})
        assert resp.status_code == 200
        assert resp.json()["compliant"] is True

    async def test_export_user_data_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/compliance/export", json={"user_id": "export-user"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "export-user"

    async def test_create_deletion_request_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/compliance/deletion-request", json={"user_id": "del-user", "reason": "Testing"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_pii_fields_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/pii-fields")
        assert resp.status_code == 200
        assert "email" in resp.json()["fields"]

    async def test_compliance_report_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/compliance/report", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Mandate Finder API"
        assert "encryption" in data
        assert "retention_policies" in data
        assert "legal_bases" in data

    async def test_cold_contact_guidelines_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/guidelines/cold-contact")
        assert resp.status_code == 200
        assert "§7 UWG" in resp.json()["regulation"]

    async def test_encryption_info_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/compliance/encryption", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["algorithm"] == "AES-256-GCM"

    async def test_encryption_key_rotation_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/compliance/encryption/rotate", json={}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "rotated"

    async def test_record_of_processing_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/compliance/record-of-processing", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["article"] == "Art. 30 DSGVO"

    async def test_data_breach_procedure_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/data-breach-procedure")
        assert resp.status_code == 200
        assert "72 hours" in resp.json()["notification_timeline"]

    async def test_dpia_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/dpia")
        assert resp.status_code == 200
        assert len(resp.json()["risks_identified"]) >= 2

    async def test_compliance_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "encryption_key" in data["checks"]

    async def test_avv_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/avv")
        assert resp.status_code == 200
        assert "Auftragsverarbeitungsvertrag" in resp.json()["title"]

    async def test_data_localization_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/compliance/data-localization")
        assert resp.status_code == 200
        assert "Germany" in resp.json()["data_residency"]

    async def test_compliance_events_module(self):
        from src.compliance.events import COMPLIANCE_EVENTS
        assert "deletion.completed" in COMPLIANCE_EVENTS
        assert len(COMPLIANCE_EVENTS) == 4

    async def test_webhook_valid_events_includes_compliance(self):
        from src.api.v1.webhooks import VALID_EVENTS
        for event in ("deletion.completed", "deletion.failed", "consent.revoked", "optout.registered"):
            assert event in VALID_EVENTS

    async def test_csv_export_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/compliance/export", json={"user_id": "csv-test", "format": "csv"}, headers=auth_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "csv-test" in resp.headers.get("content-disposition", "")

    async def test_audit_middleware_exists(self):
        from src.middleware.audit import COMPLIANCE_ENDPOINTS, PublicOptOutRateLimiter
        assert "/api/v1/compliance/export" in COMPLIANCE_ENDPOINTS
        limiter = PublicOptOutRateLimiter()
        assert await limiter.check("127.0.0.1", limit=100, window=3600) is True

    def test_encryption_key_rotation_in_memory(self):
        plaintext = "pre-rotation@example.com"
        encrypted = encrypt_field(plaintext)
        assert decrypt_field(encrypted) == plaintext
        result = rotate_encryption_key()
        assert result["status"] == "rotated"
        assert result["previous_key_hash"] != result["new_key_hash"]


class TestE2EDeletionFlow:
    async def test_full_deletion_lifecycle(self, test_session_factory: async_sessionmaker, client: AsyncClient):
        from src.core.security import hash_api_key
        from src.db.models import APIKey
        async with test_session_factory() as session:
            key_hash = hash_api_key("e2e-test-key")
            api_key = APIKey(key_hash=key_hash, name="E2E User", scopes=["*"], tier="professional")
            session.add(api_key)
            await session.commit()
            user_id = api_key.id
        headers = {"Authorization": "Bearer e2e-test-key"}
        export_resp = await client.post("/api/v1/compliance/export", json={"user_id": user_id}, headers=headers)
        assert export_resp.status_code == 200
        deletion_resp = await client.post("/api/v1/compliance/deletion-request", json={"user_id": user_id, "reason": "Art. 17 DSGVO"}, headers=headers)
        assert deletion_resp.status_code == 200
        request_id = deletion_resp.json()["id"]
        process_resp = await client.post(f"/api/v1/compliance/deletion-requests/{request_id}/process?user_id={user_id}", headers=headers)
        assert process_resp.status_code == 200
        assert process_resp.json()["status"] == "completed"
        async with test_session_factory() as session:
            result = await session.execute(select(APIKey).where(APIKey.id == user_id))
            deleted_key = result.scalar_one_or_none()
            assert deleted_key.name == "[DELETED]"

    async def test_company_opt_out_block_outreach(self, test_session_factory: async_sessionmaker, client: AsyncClient):
        resp = await client.post("/api/v1/compliance/opt-out", json={"company_domain": "e2e-optout.de"})
        assert resp.status_code == 200
        uwg_resp = await client.post("/api/v1/compliance/check-uwg", json={"company_domain": "e2e-optout.de"})
        assert uwg_resp.status_code == 200
        assert uwg_resp.json()["compliant"] is False
