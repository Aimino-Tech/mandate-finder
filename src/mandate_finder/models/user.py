from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mandate_finder.database import Base, JsonType


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    propelauth_user_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    user_type: Mapped[str] = mapped_column(String(50), default="trial")
    information: Mapped[dict[str, object]] = mapped_column(JsonType, default=dict)
    settings: Mapped[dict[str, object]] = mapped_column(JsonType, default=dict)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="users"
    )


from mandate_finder.models.organization import Organization  # noqa: E402, F811
