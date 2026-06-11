from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.compliance.consent_manager import ConsentManager
from src.db.models import APIKey, OutreachCampaign, OutreachMessage, RecipientProfile
from src.services.outreach.compliance import OutreachComplianceService
from src.services.outreach.generator import PersonalizationContext, generate_message
from src.services.outreach.templates import OutreachTemplateService

CAMPAIGN_STATUSES = {"draft", "generating", "review", "approved", "sending", "active", "paused", "completed", "cancelled"}
MESSAGE_STATUSES = {"draft", "approved", "sent", "bounced", "opened", "replied"}


class CampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        api_key_id: str,
        name: str,
        target_company_name: str,
        target_company_domain: str = "",
        target_industry: str | None = None,
        tone: str = "professional",
    ) -> OutreachCampaign:
        campaign = OutreachCampaign(
            api_key_id=api_key_id,
            name=name,
            target_company_name=target_company_name,
            target_company_domain=target_company_domain,
            target_industry=target_industry,
            tone=tone,
        )
        self.session.add(campaign)
        await self.session.commit()
        await self.session.refresh(campaign)
        return campaign

    async def get(self, campaign_id: str) -> OutreachCampaign | None:
        result = await self.session.execute(
            select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
        )
        return result.scalar_one_or_none()

    async def list_campaigns(
        self,
        api_key: APIKey | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[OutreachCampaign]:
        query = select(OutreachCampaign)
        if api_key is not None:
            query = query.where(OutreachCampaign.api_key_id == api_key.id)
        if status:
            query = query.where(OutreachCampaign.status == status)
        query = query.order_by(OutreachCampaign.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, campaign_id: str, **kwargs: Any) -> OutreachCampaign | None:
        campaign = await self.get(campaign_id)
        if campaign is None:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(campaign, key):
                setattr(campaign, key, value)
        await self.session.commit()
        await self.session.refresh(campaign)
        return campaign

    async def delete(self, campaign_id: str) -> bool:
        campaign = await self.get(campaign_id)
        if campaign is None:
            return False
        await self.session.delete(campaign)
        await self.session.commit()
        return True

    async def add_recipient(
        self,
        campaign_id: str,
        first_name: str,
        last_name: str,
        title: str,
        email: str,
        company_name: str,
        company_domain: str = "",
        phone: str | None = None,
        linkedin_url: str | None = None,
        confidence_score: float = 0.0,
        source_enrichment_id: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> RecipientProfile | None:
        campaign = await self.get(campaign_id)
        if campaign is None:
            return None
        profile = RecipientProfile(
            campaign_id=campaign_id,
            source_enrichment_id=source_enrichment_id,
            first_name=first_name,
            last_name=last_name,
            title=title,
            email=email,
            phone=phone,
            linkedin_url=linkedin_url,
            company_name=company_name or campaign.target_company_name,
            company_domain=company_domain or campaign.target_company_domain,
            confidence_score=confidence_score,
            raw_data=raw_data,
        )
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def list_recipients(
        self, campaign_id: str, offset: int = 0, limit: int = 50
    ) -> list[RecipientProfile]:
        result = await self.session.execute(
            select(RecipientProfile)
            .where(RecipientProfile.campaign_id == campaign_id)
            .order_by(RecipientProfile.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result_list: list[RecipientProfile] = list(result.scalars().all())
        return result_list

    async def list_messages(
        self, campaign_id: str, offset: int = 0, limit: int = 50
    ) -> list[OutreachMessage]:
        result = await self.session.execute(
            select(OutreachMessage)
            .where(OutreachMessage.campaign_id == campaign_id)
            .order_by(OutreachMessage.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result_list: list[OutreachMessage] = list(result.scalars().all())
        return result_list

    async def generate_messages(
        self,
        campaign_id: str,
        template_id: str | None = None,
        tone: str | None = None,
        motivation_reason: str = "",
        market_signals: list[str] | None = None,
    ) -> list[OutreachMessage]:
        campaign = await self.get(campaign_id)
        if campaign is None:
            return []

        campaign.status = "generating"
        await self.session.commit()

        recipients = await self.list_recipients(campaign_id)
        template_service = OutreachTemplateService(self.session)
        template = await template_service.get(template_id) if template_id else None
        signals: list[str] = market_signals or []

        compliance_service = OutreachComplianceService(self.session)
        consent_manager = ConsentManager(self.session)
        company_domain = campaign.target_company_domain

        messages: list[OutreachMessage] = []
        for recipient in recipients:
            context = PersonalizationContext(
                recipient_first_name=recipient.first_name,
                recipient_last_name=recipient.last_name,
                recipient_title=recipient.title,
                recipient_email=recipient.email,
                company_name=recipient.company_name or campaign.target_company_name,
                company_domain=company_domain or recipient.company_domain,
                company_industry=campaign.target_industry or "",
                motivation_reason=motivation_reason,
                market_signals=signals,
            )

            opt_out_ok = await compliance_service.check_opt_out(company_domain or recipient.company_domain)
            user_id = recipient.id
            has_consent = await consent_manager.has_valid_consent(user_id, "marketing") if user_id else True
            compliance_passed = opt_out_ok and has_consent

            result = await generate_message(
                template_subject=template.subject_template if template else "{{first_name}}, let's connect",
                template_body=template.body_template if template else "Dear {{first_name}},\n\nI wanted to reach out...",
                context=context,
                tone=tone or campaign.tone,
            )

            body_text, body_html = compliance_service.append_disclaimer(
                result.body_text,
                result.body_text.replace("\n", "<br>\n"),
            )

            msg = OutreachMessage(
                campaign_id=campaign_id,
                template_id=template.id if template else None,
                recipient_profile_id=recipient.id,
                subject=result.subject,
                body_text=body_text,
                body_html=body_html,
                channel="email",
                tone=tone or campaign.tone,
                personalization_context={
                    "recipient_email": recipient.email,
                    "company_name": recipient.company_name,
                    "motivation_reason": motivation_reason,
                    "market_signals_count": len(signals),
                },
                status="draft",
                generated_by_model=result.model,
                token_count=result.total_tokens,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
                compliance_check_passed=compliance_passed,
            )
            self.session.add(msg)
            messages.append(msg)

        campaign.status = "review"
        campaign.total_messages = len(messages)
        await self.session.commit()

        for msg in messages:
            await self.session.refresh(msg)
        return messages

    async def approve_messages(self, campaign_id: str) -> bool:
        campaign = await self.get(campaign_id)
        if campaign is None:
            return False
        messages = await self.list_messages(campaign_id)
        for msg in messages:
            msg.status = "approved"
        campaign.status = "approved"
        await self.session.commit()
        return True

    async def send_messages(self, campaign_id: str) -> bool:
        campaign = await self.get(campaign_id)
        if campaign is None:
            return False
        messages = await self.list_messages(campaign_id)
        now = datetime.now(UTC)
        for msg in messages:
            if msg.status == "approved":
                msg.status = "sent"
        campaign.status = "active"
        campaign.sent_at = now
        campaign.sent_count = sum(1 for m in messages if m.status == "sent")
        await self.session.commit()
        return True

    async def pause_campaign(self, campaign_id: str) -> bool:
        campaign = await self.get(campaign_id)
        if campaign is None or campaign.status != "active":
            return False
        campaign.status = "paused"
        await self.session.commit()
        return True

    async def resume_campaign(self, campaign_id: str) -> bool:
        campaign = await self.get(campaign_id)
        if campaign is None or campaign.status != "paused":
            return False
        campaign.status = "active"
        await self.session.commit()
        return True
