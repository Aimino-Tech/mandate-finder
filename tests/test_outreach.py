from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.security import generate_api_key
from src.db.models import APIKey
from src.services.outreach.templates import OutreachTemplateService, extract_variables, render_template


class TestTemplateUtils:
    def test_extract_variables(self):
        assert extract_variables("Hello {{name}}, your role is {{title}}") == ["name", "title"]

    def test_extract_variables_no_matches(self):
        assert extract_variables("Hello world") == []

    def test_extract_variables_empty(self):
        assert extract_variables("") == []

    def test_render_template(self):
        result = render_template("Hello {{name}}!", {"name": "Anna"})
        assert result == "Hello Anna!"

    def test_render_template_missing_variable(self):
        result = render_template("Hello {{name}}!", {})
        assert result == "Hello {{name}}!"

    def test_render_template_multiple(self):
        result = render_template("{{greeting}} {{name}}!", {"greeting": "Hi", "name": "Max"})
        assert result == "Hi Max!"


class TestTemplateService:
    async def test_create_template(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            template = await service.create(
                name="Test Template",
                subject_template="Hello {{first_name}}",
                body_template="Dear {{first_name}},\n\nWe are {{company_name}}.",
                channel="email",
                tone="professional",
            )
            assert template.id is not None
            assert template.name == "Test Template"
            assert "first_name" in (template.variables_schema or [])
            assert "company_name" in (template.variables_schema or [])

    async def test_get_template(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            created = await service.create(
                name="Get Test", subject_template="Hi {{name}}", body_template="Body {{name}}"
            )
            fetched = await service.get(created.id)
            assert fetched is not None
            assert fetched.name == "Get Test"

    async def test_get_template_not_found(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            assert await service.get("nonexistent") is None

    async def test_list_templates(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            await service.create(name="T1", subject_template="S1", body_template="B1")
            await service.create(name="T2", subject_template="S2", body_template="B2")
            templates = await service.list()
            assert len(templates) >= 2

    async def test_update_template(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            created = await service.create(
                name="Original", subject_template="Hi {{name}}", body_template="Body {{name}}"
            )
            updated = await service.update(created.id, name="Updated Name")
            assert updated is not None
            assert updated.name == "Updated Name"

    async def test_delete_template(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            created = await service.create(name="To Delete", subject_template="S", body_template="B")
            assert await service.delete(created.id) is True
            fetched = await service.get(created.id)
            assert fetched is not None
            assert fetched.is_active is False

    async def test_preview(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            service = OutreachTemplateService(session)
            created = await service.create(
                name="Preview Test",
                subject_template="Hello {{first_name}}",
                body_template="Dear {{first_name}},\n\nWelcome to {{company_name}}!",
            )
            result = await service.preview(created.id, {"first_name": "Anna", "company_name": "Siemens"})
            assert result is not None
            assert result["subject"] == "Hello Anna"
            assert "Siemens" in result["body_text"]


class TestCampaignService:
    async def test_create_campaign(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            from src.core.security import hash_api_key
            from src.services.outreach.campaign import CampaignService
            key_hash = hash_api_key("test-key")
            key = APIKey(key_hash=key_hash, name="Test", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            service = CampaignService(session)
            campaign = await service.create(
                api_key_id=key.id,
                name="Test Campaign",
                target_company_name="Siemens",
                target_company_domain="siemens.com",
                target_industry="Industrial",
            )
            assert campaign.id is not None
            assert campaign.name == "Test Campaign"
            assert campaign.status == "draft"

    async def test_add_recipient(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            from src.core.security import hash_api_key
            from src.services.outreach.campaign import CampaignService
            key_hash = hash_api_key("test-key-2")
            key = APIKey(key_hash=key_hash, name="Test2", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            service = CampaignService(session)
            campaign = await service.create(api_key_id=key.id, name="Recip Test", target_company_name="TestCo")
            recipient = await service.add_recipient(
                campaign_id=campaign.id,
                first_name="Anna",
                last_name="Schmidt",
                title="HR Director",
                email="anna@testco.com",
                company_name="TestCo",
            )
            assert recipient is not None
            assert recipient.first_name == "Anna"
            assert recipient.email == "anna@testco.com"

    async def test_generate_messages_no_recipients(self, test_session_factory: async_sessionmaker):
        async with test_session_factory() as session:
            from src.core.security import hash_api_key
            from src.services.outreach.campaign import CampaignService
            key_hash = hash_api_key("test-key-3")
            key = APIKey(key_hash=key_hash, name="Test3", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            service = CampaignService(session)
            campaign = await service.create(api_key_id=key.id, name="Empty Gen", target_company_name="TestCo")
            messages = await service.generate_messages(campaign.id)
            assert messages == []


@pytest.fixture
async def agency_api_key(test_session_factory: async_sessionmaker):
    async with test_session_factory() as session:
        raw, key_hash = generate_api_key()
        api_key = APIKey(key_hash=key_hash, name="Outreach Test Key", tier="agency")
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)
    return raw


@pytest.fixture
async def auth_headers(agency_api_key):
    return {"Authorization": f"Bearer {agency_api_key}"}


class TestTemplatesAPI:
    async def test_create_template(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/outreach/templates",
            json={
                "name": "API Test Template",
                "subject_template": "Hello {{name}}",
                "body_template": "Dear {{name}},\n\nWelcome!",
                "channel": "email",
                "tone": "professional",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "API Test Template"

    async def test_create_template_empty_name(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/outreach/templates",
            json={"name": "  ", "subject_template": "S", "body_template": "B"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_get_template(self, client: AsyncClient, auth_headers):
        create_resp = await client.post(
            "/api/v1/outreach/templates",
            json={"name": "Get Tpl", "subject_template": "Hi {{n}}", "body_template": "Body {{n}}"},
            headers=auth_headers,
        )
        tpl_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/outreach/templates/{tpl_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == tpl_id

    async def test_delete_template(self, client: AsyncClient, auth_headers):
        create_resp = await client.post(
            "/api/v1/outreach/templates",
            json={"name": "Del Tpl", "subject_template": "S", "body_template": "B"},
            headers=auth_headers,
        )
        tpl_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/outreach/templates/{tpl_id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_no_auth_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/outreach/templates",
            json={"name": "No Auth", "subject_template": "S", "body_template": "B"},
        )
        assert resp.status_code == 401

    async def test_create_campaign(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": "API Campaign", "target_company_name": "Siemens"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "API Campaign"
        assert resp.json()["status"] == "draft"

    async def test_add_recipient_to_campaign(self, client: AsyncClient, auth_headers):
        camp_resp = await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": "Recip Camp", "target_company_name": "Siemens"},
            headers=auth_headers,
        )
        camp_id = camp_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/outreach/campaigns/{camp_id}/recipients",
            json={
                "first_name": "Anna",
                "last_name": "Schmidt",
                "title": "HR Director",
                "email": "anna@siemens.com",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["first_name"] == "Anna"

    async def test_approve_campaign(self, client: AsyncClient, auth_headers):
        camp_resp = await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": "Approve Camp", "target_company_name": "Siemens"},
            headers=auth_headers,
        )
        camp_id = camp_resp.json()["id"]
        resp = await client.post(f"/api/v1/outreach/campaigns/{camp_id}/approve", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_send_campaign(self, client: AsyncClient, auth_headers):
        camp_resp = await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": "Send Camp", "target_company_name": "Siemens"},
            headers=auth_headers,
        )
        camp_id = camp_resp.json()["id"]
        template_resp = await client.post(
            "/api/v1/outreach/templates",
            json={"name": "Send Tpl", "subject_template": "Hi {{name}}", "body_template": "Body {{name}}"},
            headers=auth_headers,
        )
        template_id = template_resp.json()["id"]
        await client.post(
            f"/api/v1/outreach/campaigns/{camp_id}/recipients",
            json={"first_name": "Anna", "last_name": "S", "title": "HR", "email": "anna@siemens.com"},
            headers=auth_headers,
        )
        await client.post(
            f"/api/v1/outreach/campaigns/{camp_id}/generate",
            json={"template_id": template_id},
            headers=auth_headers,
        )
        await client.post(f"/api/v1/outreach/campaigns/{camp_id}/approve", headers=auth_headers)
        resp = await client.post(f"/api/v1/outreach/campaigns/{camp_id}/send", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        assert resp.json()["sent_count"] > 0

    async def test_pause_resume_campaign(self, client: AsyncClient, auth_headers):
        camp_resp = await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": "Pause Camp", "target_company_name": "Siemens"},
            headers=auth_headers,
        )
        camp_id = camp_resp.json()["id"]
        template_resp = await client.post(
            "/api/v1/outreach/templates",
            json={"name": "Pause Tpl", "subject_template": "Hi {{n}}", "body_template": "Body {{n}}"},
            headers=auth_headers,
        )
        template_id = template_resp.json()["id"]
        await client.post(
            f"/api/v1/outreach/campaigns/{camp_id}/recipients",
            json={"first_name": "Max", "last_name": "M", "title": "HR", "email": "max@siemens.com"},
            headers=auth_headers,
        )
        await client.post(
            f"/api/v1/outreach/campaigns/{camp_id}/generate",
            json={"template_id": template_id},
            headers=auth_headers,
        )
        await client.post(f"/api/v1/outreach/campaigns/{camp_id}/approve", headers=auth_headers)
        await client.post(f"/api/v1/outreach/campaigns/{camp_id}/send", headers=auth_headers)
        pause_resp = await client.post(f"/api/v1/outreach/campaigns/{camp_id}/pause", headers=auth_headers)
        assert pause_resp.status_code == 200
        assert pause_resp.json()["status"] == "paused"
        resume_resp = await client.post(f"/api/v1/outreach/campaigns/{camp_id}/resume", headers=auth_headers)
        assert resume_resp.status_code == 200
        assert resume_resp.json()["status"] == "active"


class TestComplianceIntegration:
    async def test_compliance_disclaimer_appended(self, test_session_factory: async_sessionmaker):
        from src.services.outreach.compliance import OutreachComplianceService
        async with test_session_factory() as session:
            service = OutreachComplianceService(session)
            body_text, body_html = service.append_disclaimer("Hello", "Hello")
            assert "§7 UWG" in body_text
            assert "§7 UWG" in body_html
            assert body_text.startswith("Hello")

    async def test_check_opt_out_not_opted(self, test_session_factory: async_sessionmaker):
        from src.services.outreach.compliance import OutreachComplianceService
        async with test_session_factory() as session:
            service = OutreachComplianceService(session)
            result = await service.check_opt_out("nonexistent-company.com")
            assert result is True

    async def test_check_opt_out_opted(self, test_session_factory: async_sessionmaker):
        from src.compliance.consent_manager import ConsentManager
        from src.services.outreach.compliance import OutreachComplianceService
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            await manager.register_opt_out(company_domain="opted-out.com")
            service = OutreachComplianceService(session)
            result = await service.check_opt_out("opted-out.com")
            assert result is False

    async def test_compliance_check_passed(self, test_session_factory: async_sessionmaker):
        from src.services.outreach.compliance import OutreachComplianceService
        async with test_session_factory() as session:
            service = OutreachComplianceService(session)
            result = await service.check_compliance(
                company_domain="example.com",
                recipient_email="test@example.com",
            )
            assert result.passed is True
            assert result.opt_out_checked is True

    async def test_compliance_check_blocked_by_opt_out(self, test_session_factory: async_sessionmaker):
        from src.compliance.consent_manager import ConsentManager
        from src.services.outreach.compliance import OutreachComplianceService
        async with test_session_factory() as session:
            manager = ConsentManager(session)
            await manager.register_opt_out(company_domain="blocked.de")
            service = OutreachComplianceService(session)
            result = await service.check_compliance(company_domain="blocked.de")
            assert result.passed is False
            assert len(result.issues) > 0
            assert "opt-out" in result.issues[0].lower()


class TestDeliveryTracking:
    async def test_campaign_delivery_status(self, test_session_factory: async_sessionmaker):
        from src.core.security import hash_api_key
        from src.services.outreach.campaign import CampaignService
        async with test_session_factory() as session:
            key_hash = hash_api_key("del-test-key")
            key = APIKey(key_hash=key_hash, name="Del Test", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            service = CampaignService(session)
            campaign = await service.create(api_key_id=key.id, name="Del Camp", target_company_name="DelCo")
            await service.add_recipient(
                campaign_id=campaign.id, first_name="Max", last_name="M", title="HR",
                email="max@delco.com", company_name="DelCo",
            )
            assert await service.approve_messages(campaign.id) is True

    async def test_send_updates_count(self, test_session_factory: async_sessionmaker):
        from src.core.security import hash_api_key
        from src.services.outreach.campaign import CampaignService
        async with test_session_factory() as session:
            key_hash = hash_api_key("send-count-key")
            key = APIKey(key_hash=key_hash, name="Send Count", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            service = CampaignService(session)
            campaign = await service.create(api_key_id=key.id, name="Send Count", target_company_name="SCo")
            await service.add_recipient(
                campaign_id=campaign.id, first_name="Lena", last_name="M", title="HR",
                email="lena@sco.com", company_name="SCo",
            )
            await service.generate_messages(campaign.id)
            await service.approve_messages(campaign.id)
            assert await service.send_messages(campaign.id) is True
            updated = await service.get(campaign.id)
            assert updated is not None
            assert updated.status == "active"
            assert updated.sent_count == 1

    async def test_create_delivery(self, test_session_factory: async_sessionmaker):
        from src.core.security import hash_api_key
        from src.services.outreach.campaign import CampaignService
        from src.services.outreach.delivery import DeliveryService
        async with test_session_factory() as session:
            key_hash = hash_api_key("del-svc-key")
            key = APIKey(key_hash=key_hash, name="Del Svc", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            camp_service = CampaignService(session)
            campaign = await camp_service.create(api_key_id=key.id, name="Del Svc", target_company_name="DS")
            await camp_service.add_recipient(
                campaign_id=campaign.id, first_name="X", last_name="Y", title="HR",
                email="x@ds.com", company_name="DS",
            )
            msgs = await camp_service.generate_messages(campaign.id)
            assert len(msgs) > 0
            msg_id = msgs[0].id
            service = DeliveryService(session)
            delivery = await service.create_delivery(msg_id, "recipient@test.com")
            assert delivery is not None
            assert delivery.status == "pending"
            assert delivery.recipient_email == "recipient@test.com"

    async def test_update_delivery_status(self, test_session_factory: async_sessionmaker):
        from src.core.security import hash_api_key
        from src.services.outreach.campaign import CampaignService
        from src.services.outreach.delivery import DeliveryService
        async with test_session_factory() as session:
            key_hash = hash_api_key("upd-del-key")
            key = APIKey(key_hash=key_hash, name="Upd Del", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            camp_service = CampaignService(session)
            campaign = await camp_service.create(api_key_id=key.id, name="Upd Del", target_company_name="UD")
            await camp_service.add_recipient(
                campaign_id=campaign.id, first_name="A", last_name="B", title="HR",
                email="a@ud.com", company_name="UD",
            )
            msgs = await camp_service.generate_messages(campaign.id)
            msg_id = msgs[0].id
            service = DeliveryService(session)
            delivery = await service.create_delivery(msg_id, "test@ud.com")
            updated = await service.update_status(delivery.id, "sent")
            assert updated is not None
            assert updated.status == "sent"
            assert updated.sent_at is not None

    async def test_create_variant(self, test_session_factory: async_sessionmaker):
        from src.core.security import hash_api_key
        from src.services.outreach.campaign import CampaignService
        from src.services.outreach.delivery import VariantService
        async with test_session_factory() as session:
            key_hash = hash_api_key("var-test-key")
            key = APIKey(key_hash=key_hash, name="Var Test", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            camp_service = CampaignService(session)
            campaign = await camp_service.create(api_key_id=key.id, name="Var Test", target_company_name="VT")
            await camp_service.add_recipient(
                campaign_id=campaign.id, first_name="V", last_name="T", title="HR",
                email="v@vt.com", company_name="VT",
            )
            msgs = await camp_service.generate_messages(campaign.id)
            msg_id = msgs[0].id
            service = VariantService(session)
            variant = await service.create_variant(msg_id, "B", "Alt Subject", "Alt body")
            assert variant is not None
            assert variant.variant_label == "B"
            assert variant.subject == "Alt Subject"

    async def test_declare_winner(self, test_session_factory: async_sessionmaker):
        from src.core.security import hash_api_key
        from src.services.outreach.campaign import CampaignService
        from src.services.outreach.delivery import VariantService
        async with test_session_factory() as session:
            key_hash = hash_api_key("win-test-key")
            key = APIKey(key_hash=key_hash, name="Win Test", tier="solo")
            session.add(key)
            await session.commit()
            await session.refresh(key)
            camp_service = CampaignService(session)
            campaign = await camp_service.create(api_key_id=key.id, name="Win Test", target_company_name="WT")
            await camp_service.add_recipient(
                campaign_id=campaign.id, first_name="W", last_name="T", title="HR",
                email="w@wt.com", company_name="WT",
            )
            msgs = await camp_service.generate_messages(campaign.id)
            msg_id = msgs[0].id
            service = VariantService(session)
            v1 = await service.create_variant(msg_id, "A", "Sub A", "Body A")
            v2 = await service.create_variant(msg_id, "B", "Sub B", "Body B")
            await service.score_variant(v1.id, 8.5)
            await service.score_variant(v2.id, 9.0)
            winner = await service.declare_winner(v2.id)
            assert winner is not None
            assert winner.is_winner is True
            assert winner.variant_label == "B"



