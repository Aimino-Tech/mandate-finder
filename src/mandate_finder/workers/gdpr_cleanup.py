"""GDPR Art 17 deletion worker.

Cascading delete of all user data while preserving organization integrity.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.integrations.propelauth import PropelauthClient
from mandate_finder.models.audit_log import AuditLog
from mandate_finder.models.organization import OrganizationMember
from mandate_finder.models.user import User

logger = logging.getLogger(__name__)


async def gdpr_delete_user(
    db: AsyncSession,
    user_id: UUID,
    delete_from_propelauth: bool = True,
) -> None:
    """Delete all data belonging to a user.

    Preserves the organization and other members' data.
    Removes the user from Propelauth if requested.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("GDPR delete: user %s not found", user_id)
        return

    propelauth_user_id = user.propelauth_user_id

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id
        )
    )
    for member in result.scalars().all():
        await db.delete(member)

    result = await db.execute(
        select(AuditLog).where(AuditLog.user_id == user.id)
    )
    for entry in result.scalars().all():
        await db.delete(entry)

    await db.delete(user)
    await db.commit()

    if delete_from_propelauth and propelauth_user_id:
        try:
            client = PropelauthClient()
            await client.delete_user(propelauth_user_id)
        except Exception as e:
            logger.error(
                "Failed to delete user %s from Propelauth: %s",
                propelauth_user_id,
                e,
            )

    logger.info("GDPR deletion complete for user %s", user_id)
