from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.compliance.consent_manager import ConsentManager
from src.compliance.data_governance import DataGovernance, DataType

COMPLIANCE_DISCLAIMER_TEXT = """
---
This message is intended for business purposes. You can unsubscribe at any time by replying to this email. We respect your privacy and comply with §7 UWG (Germany) and applicable data protection regulations.
"""

COMPLIANCE_DISCLAIMER_HTML = """
<hr>
<p style="font-size:11px;color:#666;">
This message is intended for business purposes. You can unsubscribe at any time by replying to this email.
We respect your privacy and comply with §7 UWG (Germany) and applicable data protection regulations.
</p>
"""


@dataclass
class ComplianceCheckResult:
    passed: bool = False
    opt_out_checked: bool = False
    consent_checked: bool = False
    disclaimer_appended: bool = False
    issues: list[str] = field(default_factory=list)


class OutreachComplianceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._consent_manager = ConsentManager(session)
        self._governance = DataGovernance()

    async def check_opt_out(self, company_domain: str) -> bool:
        if not company_domain:
            return True
        return not await self._consent_manager.is_opted_out(company_domain)

    async def check_compliance(
        self,
        company_domain: str,
        recipient_email: str | None = None,
        user_id: str | None = None,
    ) -> ComplianceCheckResult:
        result = ComplianceCheckResult()

        if company_domain:
            opted_out = await self._consent_manager.is_opted_out(company_domain)
            if opted_out:
                result.issues.append(f"Company {company_domain} has registered an opt-out under §7 UWG")
            else:
                result.opt_out_checked = True

        if user_id and recipient_email:
            has_consent = await self._consent_manager.has_valid_consent(user_id, "marketing")
            if not has_consent:
                result.issues.append(f"No valid marketing consent for user {user_id}")
            else:
                result.consent_checked = True

        result.passed = len(result.issues) == 0
        return result

    def append_disclaimer(self, body_text: str, body_html: str) -> tuple[str, str]:
        return body_text + COMPLIANCE_DISCLAIMER_TEXT, body_html + COMPLIANCE_DISCLAIMER_HTML

    async def log_generation(
        self,
        message_id: str,
        compliance_result: ComplianceCheckResult,
        company_domain: str,
    ) -> None:
        await self._governance.log_retention_action(
            session=self.session,
            data_type=DataType.LOG,
            record_id=message_id,
            action="outreach_generated",
            reason=f"Outreach message generated for {company_domain}. "
                   f"Opt-out checked: {compliance_result.opt_out_checked}. "
                   f"Compliant: {compliance_result.passed}",
        )
