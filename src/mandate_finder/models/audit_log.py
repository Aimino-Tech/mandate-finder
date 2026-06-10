from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(255))
    resource_type: Mapped[str] = mapped_column(String(255))
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
