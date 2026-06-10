from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CompanyOptOut, ConsentRecord

CONSENT_PURPOSES = {
    "data_processing": "Data processing for mandate finding (Art. 6(1)(b) DSGVO)",
    "marketing": "Marketing and outreach communication (Art. 6(1)(f) DSGVO)",
    "profiling": "Automated profiling for job-matching (Art. 22 DSGVO)",
    "third_party": "Data sharing with third-party services (Art. 44 DSGVO)",
}


class ConsentManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_consent(
        self, user_id: str, purpose: str, ip_address: str, user_agent: str | None = None, expires_in_days: int | None = None
    ) -> ConsentRecord:
        if purpose not in CONSENT_PURPOSES:
            raise ValueError(f"Unknown consent purpose: {purpose}. Valid: {list(CONSENT_PURPOSES.keys())}")
        expires_at = None
        if expires_in_days:
            now = datetime.now(UTC)
            expires_at = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None) + __import__("datetime").timedelta(days=expires_in_days)
        record = ConsentRecord(user_id=user_id, purpose=purpose, ip_address=ip_address, user_agent=user_agent, expires_at=expires_at)
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def revoke_consent(self, user_id: str, purpose: str) -> bool:
        result = await self.session.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == user_id, ConsentRecord.purpose == purpose, ConsentRecord.revoked_at.is_(None))
        )
        records = result.scalars().all()
        if not records:
            return False
        now = datetime.now(UTC)
        for record in records:
            record.revoked_at = now
        await self.session.commit()
        return True

    async def has_valid_consent(self, user_id: str, purpose: str) -> bool:
        result = await self.session.execute(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.purpose == purpose,
                ConsentRecord.revoked_at.is_(None),
            )
        )
        records = result.scalars().all()
        now = datetime.now(UTC).replace(tzinfo=None)
        return any(r.expires_at is None or r.expires_at > now for r in records)

    async def get_consent_records(self, user_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == user_id).order_by(ConsentRecord.granted_at.desc())
        )
        records = result.scalars().all()
        return [
            {
                "id": r.id,
                "purpose": r.purpose,
                "purpose_description": CONSENT_PURPOSES.get(r.purpose, ""),
                "granted_at": r.granted_at.isoformat(),
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                "is_valid": (r.revoked_at is None and (r.expires_at is None or r.expires_at > datetime.now(UTC).replace(tzinfo=None))),
            }
            for r in records
        ]

    async def register_opt_out(self, company_domain: str, company_name: str | None = None, contact_email: str | None = None, reason: str | None = None) -> CompanyOptOut:
        existing = await self.get_opt_out(company_domain)
        if existing and existing.is_active:
            raise ValueError(f"Company {company_domain} is already opted out")
        opt_out = CompanyOptOut(company_domain=company_domain, company_name=company_name, contact_email=contact_email, reason=reason)
        self.session.add(opt_out)
        await self.session.commit()
        await self.session.refresh(opt_out)
        return opt_out

    async def get_opt_out(self, company_domain: str) -> CompanyOptOut | None:
        result = await self.session.execute(
            select(CompanyOptOut).where(CompanyOptOut.company_domain == company_domain, CompanyOptOut.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def is_opted_out(self, company_domain: str) -> bool:
        opt_out = await self.get_opt_out(company_domain)
        return opt_out is not None

    async def verify_opt_out(self, company_domain: str) -> bool:
        result = await self.session.execute(
            select(CompanyOptOut).where(CompanyOptOut.company_domain == company_domain, CompanyOptOut.is_active.is_(True))
        )
        opt_out = result.scalar_one_or_none()
        if opt_out is None:
            return False
        opt_out.verified_at = datetime.now(UTC)
        await self.session.commit()
        return True

    async def remove_opt_out(self, company_domain: str) -> bool:
        result = await self.session.execute(
            select(CompanyOptOut).where(CompanyOptOut.company_domain == company_domain, CompanyOptOut.is_active.is_(True))
        )
        opt_out = result.scalar_one_or_none()
        if opt_out is None:
            return False
        opt_out.is_active = False
        await self.session.commit()
        return True

    async def list_opt_outs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(CompanyOptOut).where(CompanyOptOut.is_active.is_(True)).order_by(CompanyOptOut.registered_at.desc()).limit(limit).offset(offset)
        )
        opt_outs = result.scalars().all()
        return [
            {
                "id": o.id,
                "company_domain": o.company_domain,
                "company_name": o.company_name,
                "reason": o.reason,
                "registered_at": o.registered_at.isoformat(),
                "verified_at": o.verified_at.isoformat() if o.verified_at else None,
            }
            for o in opt_outs
        ]

    @staticmethod
    def check_uwg_compliance(company_domain: str, opted_out: bool) -> dict[str, Any]:
        return {
            "company_domain": company_domain,
            "opted_out": opted_out,
            "compliant": not opted_out,
            "message": "Contact is §7 UWG compliant"
            if not opted_out
            else "Company has registered an opt-out. Outreach is not permitted under §7 UWG.",
        }
