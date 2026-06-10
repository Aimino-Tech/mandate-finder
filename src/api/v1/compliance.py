from __future__ import annotations

import csv as csv_module
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from src.compliance.consent_manager import CONSENT_PURPOSES, ConsentManager
from src.compliance.data_governance import DataGovernance, DataType
from src.compliance.deletion_manager import DELETED_PLACEHOLDER, DeletionManager
from src.compliance.encryption import PII_FIELDS as COMPLIANCE_PII_FIELDS
from src.config import settings
from src.db.database import async_session_factory, get_session
from src.middleware.audit import check_opt_out_rate_limit
from src.middleware.rate_limit import authenticated_api_key

router = APIRouter(prefix="/compliance", tags=["Compliance & DSGVO"])


class DataExportRequest(BaseModel):
    user_id: str
    format: str = Field(default="json", pattern="^(json|csv)$")


class DeletionRequestCreate(BaseModel):
    user_id: str
    reason: str | None = None


class OptOutRegister(BaseModel):
    company_domain: str = Field(..., description="Company domain to opt out (e.g., example.com)")
    company_name: str | None = None
    contact_email: str | None = None
    reason: str | None = None


class ConsentRecordCreate(BaseModel):
    user_id: str
    purpose: str
    ip_address: str
    user_agent: str | None = None


class UWGCheckRequest(BaseModel):
    company_domain: str


class KeyRotationRequest(BaseModel):
    new_key: str | None = Field(None, description="Base64-encoded new AES-256 key. If omitted, a random key is generated.")


@router.post("/export", summary="Export user data (Art. 20 DSGVO - Data Portability)")
async def export_user_data(body: DataExportRequest, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = DeletionManager(session)
    try:
        data = await manager.export_user_data(body.user_id)
        if body.format == "csv":
            output = io.StringIO()
            writer = csv_module.writer(output)
            writer.writerow(["section", "key", "value"])
            for section, records in data.items():
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict):
                            for k, v in record.items():
                                writer.writerow([section, k, str(v) if v else ""])
                else:
                    writer.writerow([section, "value", str(records)])
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=user-{body.user_id}-export.csv"},
            )
        return data
    except Exception as e:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/deletion-request", summary="Request account deletion (Art. 17 DSGVO - Right to Erasure)")
async def request_deletion(body: DeletionRequestCreate, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = DeletionManager(session)
    request = await manager.create_deletion_request(user_id=body.user_id, reason=body.reason)
    return {
        "id": request.id,
        "user_id": request.user_id,
        "status": request.status,
        "requested_at": request.requested_at.isoformat(),
        "message": "Deletion request received. Your data will be anonymized within 30 days.",
    }


@router.post("/deletion-requests/{request_id}/process", summary="Process a deletion request")
async def process_deletion(request_id: str, user_id: str, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = DeletionManager(session)
    try:
        result = await manager.process_deletion(user_id, request_id)
        return result
    except ValueError as e:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/deletion-status/{user_id}", summary="Check deletion status for a user")
async def get_deletion_status(user_id: str, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = DeletionManager(session)
    status = await manager.get_deletion_status(user_id)
    return {"user_id": user_id, "requests": status}


@router.get("/retention-policies", summary="List data retention policies")
async def list_retention_policies():
    governance = DataGovernance()
    return {
        "policies": {
            dt.value: {
                "type": dt.value,
                "ttl_days": policy.ttl_days,
                "action": policy.action,
                "description": _policy_description(dt),
            }
            for dt, policy in governance.policies.items()
        }
    }


def _policy_description(data_type: DataType) -> str:
    descriptions = {
        DataType.CONTACT: "Contact data (email, phone, LinkedIn): retained 24 months after last activity, then anonymized",
        DataType.SEARCH_PROFILE: "Search profiles: deleted when subscription becomes inactive",
        DataType.LOG: "System and audit logs: retained 12 months, then deleted",
        DataType.CONSENT: "Consent records: retained 10 years for legal compliance, then archived",
        DataType.DELIVERY_LOG: "Webhook delivery logs: retained 90 days, then deleted",
        DataType.USER_SESSION: "User session data: retained 6 months after last activity, then deleted",
    }
    return descriptions.get(data_type, "")


@router.post("/consent", summary="Record user consent (Art. 6 DSGVO)")
async def record_consent(body: ConsentRecordCreate, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = ConsentManager(session)
    try:
        record = await manager.record_consent(user_id=body.user_id, purpose=body.purpose, ip_address=body.ip_address, user_agent=body.user_agent)
        return {"id": record.id, "user_id": record.user_id, "purpose": record.purpose, "granted_at": record.granted_at.isoformat(), "message": f"Consent recorded for purpose: {body.purpose}"}
    except ValueError as e:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/consent/{user_id}/revoke/{purpose}", summary="Revoke consent for a purpose")
async def revoke_consent(user_id: str, purpose: str, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = ConsentManager(session)
    revoked = await manager.revoke_consent(user_id, purpose)
    if not revoked:
        raise HTTPException(HTTP_404_NOT_FOUND, detail=f"No active consent found for user {user_id} on purpose '{purpose}'")
    return {"status": "revoked", "user_id": user_id, "purpose": purpose}


@router.get("/consent/{user_id}", summary="Get all consent records for a user")
async def get_consent(user_id: str, session: AsyncSession = Depends(get_session), _api_key=Depends(authenticated_api_key)):
    manager = ConsentManager(session)
    records = await manager.get_consent_records(user_id)
    return {"user_id": user_id, "consent_records": records}


@router.post("/opt-out", summary="Register company opt-out (public, no login required)")
async def register_opt_out(
    body: OptOutRegister,
    session: AsyncSession = Depends(get_session),
    _rate_limit=Depends(check_opt_out_rate_limit),
):
    manager = ConsentManager(session)
    try:
        opt_out = await manager.register_opt_out(company_domain=body.company_domain, company_name=body.company_name, contact_email=body.contact_email, reason=body.reason)
        return {"id": opt_out.id, "company_domain": opt_out.company_domain, "status": "registered", "message": f"Opt-out registered for {body.company_domain}. Outreach to this company is blocked under §7 UWG."}
    except ValueError as e:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/opt-out", summary="List all active opt-outs")
async def list_opt_outs(limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_session)):
    manager = ConsentManager(session)
    opt_outs = await manager.list_opt_outs(limit=limit, offset=offset)
    return {"items": opt_outs, "total": len(opt_outs)}


@router.get("/opt-out/{company_domain}", summary="Check if a company has opted out")
async def check_opt_out(company_domain: str, session: AsyncSession = Depends(get_session)):
    manager = ConsentManager(session)
    opted_out = await manager.is_opted_out(company_domain)
    return ConsentManager.check_uwg_compliance(company_domain, opted_out)


@router.post("/check-uwg", summary="Check §7 UWG compliance for a company")
async def check_uwg(body: UWGCheckRequest, session: AsyncSession = Depends(get_session)):
    manager = ConsentManager(session)
    opted_out = await manager.is_opted_out(body.company_domain)
    return ConsentManager.check_uwg_compliance(body.company_domain, opted_out)


@router.get("/pii-fields", summary="List all PII fields tracked for encryption")
async def list_pii_fields():
    return {"fields": sorted(COMPLIANCE_PII_FIELDS), "encryption": "AES-256-GCM", "transit_encryption": "TLS 1.3", "note": "All PII fields are encrypted at rest."}


@router.get("/report", summary="Generate DSGVO compliance report for customer contracts")
async def compliance_report(_api_key=Depends(authenticated_api_key)):
    governance = DataGovernance()
    retention_policies = {}
    for dt, policy in governance.policies.items():
        retention_policies[dt.value] = {
            "type": dt.value,
            "ttl_days": policy.ttl_days,
            "ttl_formatted": _format_ttl(policy.ttl_days),
            "action": policy.action,
            "description": _policy_description(dt),
        }
    return {
        "service": "Mandate Finder API",
        "version": "0.1.0",
        "report_generated_at": datetime.now(UTC).isoformat(),
        "data_controller": "Customer (as defined in the AVV)",
        "data_processor": "Aimino GmbH",
        "avv_partner": settings.compliance_avv_partner,
        "encryption": {
            "at_rest": "AES-256-GCM for all PII fields",
            "in_transit": "TLS 1.3",
            "pii_fields": sorted(COMPLIANCE_PII_FIELDS),
            "deletion_placeholder": DELETED_PLACEHOLDER,
        },
        "legal_bases": {
            "data_processing": "Art. 6(1)(b) DSGVO — contract performance",
            "marketing": "Art. 6(1)(f) DSGVO — legitimate interest",
            "profiling": "Art. 22 DSGVO — automated decision-making",
            "third_party": "Art. 44 DSGVO — data transfer safeguards",
            "deletion": "Art. 17 DSGVO — right to erasure",
            "portability": "Art. 20 DSGVO — data portability",
        },
        "retention_policies": retention_policies,
        "deletion_grace_period_days": settings.compliance_deletion_grace_days,
        "auto_cleanup_interval_hours": settings.compliance_cleanup_interval_hours,
        "opt_out_mechanism": "§7 UWG compliant — public opt-out registry available at /api/v1/compliance/opt-out",
        "consent_purposes": {k: v for k, v in CONSENT_PURPOSES.items()},
    }


def _format_ttl(days: int) -> str:
    if days == 0:
        return "Immediate deletion on inactivity"
    years = days // 365
    remaining = days % 365
    months = remaining // 30
    parts = []
    if years:
        parts.append(f"{years} year(s)")
    if months:
        parts.append(f"{months} month(s)")
    return ", ".join(parts) if parts else f"{days} day(s)"


@router.get("/guidelines/cold-contact", summary="§7 UWG cold contact compliance guidelines")
async def cold_contact_guidelines():
    return {
        "regulation": "§7 UWG (Gesetz gegen den unlauteren Wettbewerb)",
        "summary": "Cold contact (email/phone) is permitted only if the recipient has not opted out and there is a legitimate interest.",
        "requirements": [
            "Recipient must not be registered in the opt-out registry",
            "Contact must include a clear opt-out/unsubscribe mechanism",
            "Sender identity must be clearly disclosed",
            "Commercial purpose must be transparent",
            "Opt-out requests must be honored immediately and permanently",
        ],
        "how_it_works_in_mandate_finder": [
            "Before sending outreach, check POST /api/v1/compliance/check-uwg with the company domain",
            "If compliant is False, outreach is NOT permitted under §7 UWG",
            "Companies can register opt-out via POST /api/v1/compliance/opt-out (public, no login)",
            "Opt-out registry is checked automatically by the compliance layer",
        ],
        "penalties": "Violations can result in cease-and-desist orders, fines up to €300,000, and competitor lawsuits.",
        "recommendation": "Always check §7 UWG compliance before initiating cold outreach. When in doubt, obtain explicit consent under Art. 6(1)(a) DSGVO.",
    }


@router.get("/encryption", summary="Get encryption key information")
async def encryption_info(_api_key=Depends(authenticated_api_key)):
    from src.compliance.encryption import get_encryption_key_info
    return get_encryption_key_info()


@router.post("/encryption/rotate", summary="Rotate encryption key")
async def rotate_key(body: KeyRotationRequest, _api_key=Depends(authenticated_api_key)):
    from src.compliance.encryption import rotate_encryption_key
    return rotate_encryption_key(new_key_b64=body.new_key)


@router.get("/record-of-processing", summary="Art. 30 DSGVO — Record of processing activities")
async def record_of_processing(_api_key=Depends(authenticated_api_key)):
    return {
        "article": "Art. 30 DSGVO",
        "requirement": "Each controller and processor shall maintain a record of processing activities.",
        "data_controller": "Customer (as defined in the AVV)",
        "data_processor": "Aimino GmbH",
        "processing_purposes": [
            "Job mandate search and discovery across public job boards",
            "Company contact enrichment via Apollo.io and similar services",
            "AI-powered job matching and relevance scoring",
            "Automated outreach campaign management",
            "Market intelligence and trend detection",
        ],
        "data_categories": [
            {"category": "User profile data", "retention": "Active while subscription active", "pii": False},
            {"category": "Contact data (email, phone, LinkedIn)", "retention": "24 months after last activity", "pii": True},
            {"category": "Company data", "retention": "24 months after last activity", "pii": False},
            {"category": "Search history and preferences", "retention": "Active while subscription active", "pii": False},
            {"category": "Consent records", "retention": "10 years", "pii": False},
            {"category": "Webhook delivery logs", "retention": "90 days", "pii": False},
            {"category": "System audit logs", "retention": "12 months", "pii": False},
        ],
        "data_subjects": ["Job seekers", "HR decision makers", "Company representatives", "Platform users"],
        "recipient_categories": ["Customer (data controller)", "Sub-processors (hosting, AI services)"],
        "third_country_transfers": "Data stored exclusively on German servers (Hetzner). No transfer to third countries without AVV.",
        "retention_periods": "See /api/v1/compliance/retention-policies for detailed retention schedules.",
    }


@router.get("/data-breach-procedure", summary="Art. 33 DSGVO — Data breach notification procedure")
async def data_breach_procedure():
    return {
        "article": "Art. 33 DSGVO",
        "requirement": "The processor shall notify the controller without undue delay after becoming aware of a personal data breach.",
        "notification_timeline": "Within 72 hours of becoming aware of the breach",
        "notification_to": "Data controller (customer) via registered contact",
        "breach_report_contents": [
            "Description of the nature of the personal data breach",
            "Categories and approximate number of data subjects concerned",
            "Categories and approximate number of personal data records concerned",
            "Name and contact details of the data protection officer",
            "Description of the likely consequences of the personal data breach",
            "Description of the measures taken or proposed to address the breach",
        ],
        "internal_procedure": [
            "1. Identify and contain the breach immediately",
            "2. Assess risk to data subjects' rights and freedoms",
            "3. Notify the data controller within 72 hours",
            "4. Document all findings and actions taken",
            "5. Cooperate with the supervisory authority",
        ],
        "contact": "Data protection incidents: security@aimino.com",
        "automation": "The compliance layer logs all data access and modification events for breach investigation.",
    }


@router.get("/dpia", summary="Art. 35 DSGVO — Data Protection Impact Assessment")
async def dpia_documentation():
    return {
        "article": "Art. 35 DSGVO",
        "requirement": "A Data Protection Impact Assessment shall be carried out where processing is likely to result in high risk to natural persons.",
        "assessment_summary": "Mandate Finder processes personal data for job matching and outreach. A DPIA is recommended due to automated profiling (Art. 22).",
        "risks_identified": [
            {"risk": "Automated profiling of job seekers", "mitigation": "Opt-out right under Art. 22, consent required for profiling", "severity": "Medium"},
            {"risk": "Enrichment of contact data from third parties", "mitigation": "Legitimate interest assessment, opt-out registry, §7 UWG checks", "severity": "Medium"},
            {"risk": "Storage of contact data for outreach campaigns", "mitigation": "24-month retention limit, AES-256 encryption at rest, automatic deletion", "severity": "Low"},
            {"risk": "Data transfer to sub-processors", "mitigation": "AVV in place with all sub-processors, German server location", "severity": "Low"},
        ],
        "recommendation": "A full DPIA should be conducted by the data controller (customer) before processing special categories of data.",
        "safeguards": [
            "AES-256-GCM encryption for all PII at rest",
            "TLS 1.3 for all data in transit",
            "Automatic data retention and deletion policies",
            "Consent management with full audit trail",
            "Company opt-out registry for §7 UWG compliance",
            "Background cleanup processes for expired data",
        ],
    }


@router.get("/health", summary="Compliance layer health check")
async def compliance_health():
    checks = {}
    overall = "healthy"
    try:
        from src.compliance.encryption import _ensure_key
        key = _ensure_key()
        checks["encryption_key"] = {"status": "ok", "key_size_bits": len(key) * 8}
    except Exception as e:
        checks["encryption_key"] = {"status": "error", "detail": str(e)}
        overall = "degraded"
    try:
        async with async_session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}
        overall = "degraded"
    try:
        from src.compliance.data_governance import DEFAULT_POLICIES
        checks["retention_policies"] = {"status": "ok", "policy_count": len(DEFAULT_POLICIES)}
    except Exception as e:
        checks["retention_policies"] = {"status": "error", "detail": str(e)}
        overall = "degraded"
    try:
        import src.middleware.audit as _audit_mod
        checks["audit_middleware"] = {"status": "ok", "endpoints_tracked": len(_audit_mod.COMPLIANCE_ENDPOINTS)}
    except Exception as e:
        checks["audit_middleware"] = {"status": "error", "detail": str(e)}
        overall = "degraded"
    try:
        from src.middleware.audit import check_opt_out_rate_limit as _check_limit
        checks["opt_out_rate_limiter"] = {"status": "ok", "importable": callable(_check_limit)}
    except Exception as e:
        checks["opt_out_rate_limiter"] = {"status": "error", "detail": str(e)}
        overall = "degraded"
    return {
        "status": overall,
        "service": "Mandate Finder Compliance Layer",
        "version": "0.1.0",
        "checks": checks,
        "recommendation": "Ensure MF_ENCRYPTION_KEY environment variable is set in production for persistent encryption.",
    }


@router.get("/avv", summary="AVV — Data Processing Agreement documentation")
async def avv_documentation():
    return {
        "title": "Auftragsverarbeitungsvertrag (AVV) — Data Processing Agreement",
        "regulation": "Art. 28 DSGVO",
        "parties": {"data_controller": "Customer (as defined in the subscription agreement)", "data_processor": "Aimino GmbH (Betreiber der Mandate Finder Plattform)"},
        "scope": "This AVV governs the processing of personal data by the Processor on behalf of the Controller through the Mandate Finder platform.",
        "processing_details": {
            "subject_matter": "HR client discovery, job mandate search, company contact enrichment, and automated outreach",
            "duration": "Duration of the subscription agreement plus data retention periods as defined in the retention policies",
            "nature_and_purpose": "Automated job matching, contact enrichment, outreach campaign management, market intelligence",
            "data_categories": ["User profile data (name, email, preferences)", "Contact data (email, phone, LinkedIn URL, company role)", "Company data (name, domain, industry, size)", "Search history and job mandate preferences", "Communication history and outreach logs"],
            "data_subjects": ["Platform users", "HR decision makers", "Job seekers", "Company representatives"],
        },
        "obligations_of_processor": [
            "Process personal data only on documented instructions from the controller",
            "Ensure confidentiality of personnel authorized to process personal data",
            "Implement appropriate technical and organizational measures (see /api/v1/compliance/report)",
            "Notify controller of any personal data breach without undue delay (see /api/v1/compliance/data-breach-procedure)",
            "Delete or return all personal data after termination of services (see /api/v1/compliance/deletion-request)",
            "Make available all information necessary to demonstrate compliance with Art. 28",
            "Maintain a record of processing activities (see /api/v1/compliance/record-of-processing)",
        ],
        "sub_processors": [
            {"name": "Hetzner Online GmbH", "location": "Nürnberg, Germany", "service": "Cloud hosting and infrastructure"},
            {"name": "OpenAI / Azure OpenAI", "location": "EU data boundary", "service": "AI-powered job matching and scoring"},
        ],
        "data_location": "All data is stored exclusively on German servers (Hetzner Online GmbH, Nuremberg data center).",
        "technical_measures": {
            "encryption_at_rest": "AES-256-GCM",
            "encryption_in_transit": "TLS 1.3",
            "access_control": "API key-based authentication with per-key scopes and rate limiting",
            "pseudonymization": "PII fields encrypted at application layer before storage",
            "backup": "Automated daily backups with 30-day retention",
            "logging": "All PII access is logged via audit middleware for accountability",
        },
    }


@router.get("/data-localization", summary="Data localization and server location documentation")
async def data_localization():
    return {
        "regulation": "DSGVO Art. 44-49 — Data transfer to third countries",
        "data_residency": "All customer data is stored exclusively in Germany.",
        "hosting_provider": {
            "name": "Hetzner Online GmbH",
            "address": "Industriestr. 25, 91710 Gunzenhausen, Germany",
            "data_center": "Nuremberg (NBG1-DC1)",
            "certification": "ISO 27001, SOC 2 Type II",
            "website": "https://www.hetzner.com",
        },
        "data_transfers": {
            "status": "No transfer of personal data to third countries outside the EU/EEA.",
            "safeguards": "If third-country transfer becomes necessary, Standard Contractual Clauses (SCC) will be executed.",
        },
        "sub_processors": [
            {
                "name": "Hetzner Online GmbH",
                "location": "Germany (Nuremberg)",
                "data": "All customer data, database storage, application hosting",
                "safeguards": "AVV in place, ISO 27001 certified, EU-based",
            },
        ],
        "compliance_statement": "Mandate Finder maintains Made in Germany data residency. All infrastructure is operated within German borders, ensuring full DSGVO compliance for German HR agencies and their customers.",
    }
