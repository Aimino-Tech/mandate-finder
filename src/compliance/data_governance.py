from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DataRetentionLog


class DataType(StrEnum):
    CONTACT = "contact"
    SEARCH_PROFILE = "search_profile"
    LOG = "log"
    CONSENT = "consent"
    DELIVERY_LOG = "delivery_log"
    USER_SESSION = "user_session"


class RetentionPolicy:
    def __init__(self, data_type: DataType, ttl_days: int, action: str = "anonymize") -> None:
        self.type = data_type
        self.ttl_days = ttl_days
        self.action = action

    def is_expired(self, last_activity: datetime | None) -> bool:
        if last_activity is None:
            return False
        cutoff = datetime.now(UTC) - timedelta(days=self.ttl_days)
        return last_activity < cutoff

    def get_cutoff_date(self) -> datetime:
        return datetime.now(UTC) - timedelta(days=self.ttl_days)


DEFAULT_POLICIES: dict[DataType, RetentionPolicy] = {
    DataType.CONTACT: RetentionPolicy(DataType.CONTACT, ttl_days=730, action="anonymize"),
    DataType.SEARCH_PROFILE: RetentionPolicy(DataType.SEARCH_PROFILE, ttl_days=0, action="delete"),
    DataType.LOG: RetentionPolicy(DataType.LOG, ttl_days=365, action="delete"),
    DataType.CONSENT: RetentionPolicy(DataType.CONSENT, ttl_days=3650, action="archive"),
    DataType.DELIVERY_LOG: RetentionPolicy(DataType.DELIVERY_LOG, ttl_days=90, action="delete"),
    DataType.USER_SESSION: RetentionPolicy(DataType.USER_SESSION, ttl_days=180, action="delete"),
}


class DataGovernance:
    def __init__(self, policies: dict[DataType, RetentionPolicy] | None = None) -> None:
        self.policies = policies or DEFAULT_POLICIES

    def get_policy(self, data_type: DataType) -> RetentionPolicy:
        return self.policies.get(data_type, DEFAULT_POLICIES[data_type])

    def is_expired(self, data_type: DataType, last_activity: datetime | None) -> bool:
        return self.get_policy(data_type).is_expired(last_activity)

    async def log_retention_action(
        self,
        session: AsyncSession,
        data_type: DataType,
        record_id: str,
        action: str,
        reason: str | None = None,
        triggered_by: str | None = None,
    ) -> DataRetentionLog:
        log = DataRetentionLog(
            data_type=data_type.value,
            record_id=record_id,
            action=action,
            reason=reason,
            triggered_by=triggered_by,
        )
        session.add(log)
        await session.commit()
        return log

    async def get_retention_logs(self, session: AsyncSession, data_type: DataType | None = None, limit: int = 100) -> list[DataRetentionLog]:
        query = select(DataRetentionLog)
        if data_type:
            query = query.where(DataRetentionLog.data_type == data_type.value)
        query = query.order_by(DataRetentionLog.performed_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    def collect_expired(self, data_type: DataType, records: list[Any], date_field: str = "updated_at") -> list[Any]:
        policy = self.get_policy(data_type)
        cutoff = policy.get_cutoff_date()
        expired = []
        for record in records:
            last_activity = getattr(record, date_field, None)
            if last_activity and last_activity < cutoff:
                expired.append(record)
        return expired
