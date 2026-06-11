from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.audit_log import AuditLog


async def write_audit_log(
    db: AsyncSession,
    user_id: UUID | None,
    organization_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, object] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        organization_id=organization_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry
