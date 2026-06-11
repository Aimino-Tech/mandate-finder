from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False, index=True
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    amount_eur: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_percentage: Mapped[int] = mapped_column(Integer, default=19)
    vat_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    total_eur: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    pdf_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
