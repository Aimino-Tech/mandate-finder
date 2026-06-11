from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class PlanTier(StrEnum):
    SOLO = "solo"
    PROFESSIONAL = "professional"
    AGENCY = "agency"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    price_monthly_eur: Mapped[int] = mapped_column(nullable=False)
    features: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
