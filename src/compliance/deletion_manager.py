from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DeletionRequest

DELETED_PLACEHOLDER = "[DELETED]"
ANONYMIZED_FIELDS = {
    "email": DELETED_PLACEHOLDER,
    "name": DELETED_PLACEHOLDER,
    "phone": None,
    "linkedin_url": None,
    "first_name": DELETED_PLACEHOLDER,
    "last_name": DELETED_PLACEHOLDER,
}


class DeletionManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_deletion_request(self, user_id: str, reason: str | None = None, deleted_by: str | None = None) -> DeletionRequest:
        request = DeletionRequest(user_id=user_id, reason=reason, status="pending", deleted_by=deleted_by)
        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def process_deletion(self, user_id: str, request_id: str) -> dict[str, Any]:
        result = await self.session.execute(select(DeletionRequest).where(DeletionRequest.id == request_id, DeletionRequest.user_id == user_id))
        request = result.scalar_one_or_none()
        if request is None:
            raise ValueError(f"Deletion request {request_id} not found for user {user_id}")
        if request.status == "completed":
            raise ValueError(f"Deletion request {request_id} already completed")
        summary = await self._anonymize_user(user_id)
        request.status = "completed"
        request.completed_at = datetime.now(UTC)
        await self.session.commit()
        summary["request_id"] = request_id
        summary["user_id"] = user_id
        summary["completed_at"] = request.completed_at.isoformat()
        await self._dispatch_webhook("deletion.completed", summary)
        return summary

    async def _anonymize_user(self, user_id: str) -> dict[str, Any]:
        anonymized_count = 0
        tables = self._get_user_tables()
        for table, id_field in tables:
            count = await self._anonymize_record(table, id_field, user_id)
            anonymized_count += count
        return {"status": "completed", "anonymized_records": anonymized_count, "tables_affected": len(tables)}

    def _get_user_tables(self) -> list[tuple[Any, str]]:
        from src.db.models import APIKey, ConsentRecord
        return [(APIKey, "id"), (ConsentRecord, "user_id")]

    async def _anonymize_record(self, model: Any, id_field: str, user_id: str) -> int:
        anonymize_values = {}
        for col in model.__table__.columns:
            col_name = col.name
            if col_name in ANONYMIZED_FIELDS:
                anonymize_values[col_name] = ANONYMIZED_FIELDS[col_name]
        if not anonymize_values:
            result = await self.session.execute(select(model).where(getattr(model, id_field) == user_id))
            record = result.scalar_one_or_none()
            if record is None:
                return 0
            await self.session.delete(record)
            return 1
        stmt = update(model).where(getattr(model, id_field) == user_id).values(**anonymize_values)
        result = await self.session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined]

    async def get_pending_requests(self, limit: int = 50) -> list[DeletionRequest]:
        result = await self.session.execute(
            select(DeletionRequest).where(DeletionRequest.status == "pending").order_by(DeletionRequest.requested_at.asc()).limit(limit)
        )
        return list(result.scalars().all())

    async def process_all_pending(self) -> list[dict[str, Any]]:
        pending = await self.get_pending_requests()
        results = []
        for request in pending:
            try:
                summary = await self.process_deletion(request.user_id, request.id)
                summary["success"] = True
            except ValueError as e:
                summary = {"request_id": request.id, "user_id": request.user_id, "success": False, "error": str(e)}
            results.append(summary)
        return results

    async def get_deletion_status(self, user_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DeletionRequest).where(DeletionRequest.user_id == user_id).order_by(DeletionRequest.requested_at.desc())
        )
        requests = result.scalars().all()
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "status": r.status,
                "reason": r.reason,
                "requested_at": r.requested_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in requests
        ]

    async def _dispatch_webhook(self, event: str, payload: dict[str, Any]) -> None:
        try:
            from src.compliance.events import dispatch_compliance_event
            await dispatch_compliance_event(event, payload)
        except Exception:
            pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        from src.db.models import APIKey, ConsentRecord
        export: dict[str, Any] = {"exported_at": datetime.now(UTC).isoformat(), "user_id": user_id}
        api_keys_result = await self.session.execute(select(APIKey).where(APIKey.id == user_id))
        keys = api_keys_result.scalars().all()
        export["api_keys"] = [
            {"id": k.id, "name": k.name, "tier": k.tier, "created_at": k.created_at.isoformat(), "is_active": k.is_active} for k in keys
        ]
        consent_result = await self.session.execute(select(ConsentRecord).where(ConsentRecord.user_id == user_id))
        consents = consent_result.scalars().all()
        export["consent_records"] = [
            {
                "id": c.id,
                "purpose": c.purpose,
                "granted_at": c.granted_at.isoformat(),
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in consents
        ]
        deletion_result = await self.session.execute(
            select(DeletionRequest).where(DeletionRequest.user_id == user_id).order_by(DeletionRequest.requested_at.desc())
        )
        deletions = deletion_result.scalars().all()
        export["deletion_requests"] = [
            {
                "id": d.id,
                "status": d.status,
                "reason": d.reason,
                "requested_at": d.requested_at.isoformat(),
                "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            }
            for d in deletions
        ]
        return export
