"""create billing tables

Revision ID: 0001
Revises:
Create Date: 2026-06-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("tier", sa.String(20), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("trial_days", sa.Integer, nullable=False, server_default="14"),
        sa.Column("features", sa.JSON, nullable=False, server_default="'{}'"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        sa.Column(
            "stripe_subscription_id", sa.String(255), nullable=True, index=True
        ),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="trialing",
        ),
        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "current_period_end",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "subscription_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("stripe_event_id", sa.String(255), nullable=True),
        sa.Column("data", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("stripe_invoice_id", sa.String(255), nullable=True, index=True),
        sa.Column("invoice_number", sa.String(50), unique=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("total_gross", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_net", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "vat_amount", sa.Numeric(10, 2), nullable=False, server_default="0"
        ),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("company_vat_id", sa.String(50), nullable=True),
        sa.Column("company_address", sa.Text, nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_url", sa.String(500), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "invoice_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price_net", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_net", sa.Numeric(10, 2), nullable=False),
    )

    op.execute(
        """
        INSERT INTO plans (id, name, tier, description, price_eur, trial_days, features, sort_order, is_active)
        VALUES
            (gen_random_uuid(), 'Solo', 'solo', 'Search only — perfect for individual recruiters', 49.00, 14, '{"features": ["search"]}', 0, true),
            (gen_random_uuid(), 'Professional', 'professional', 'Search + outreach — for active sourcing', 199.00, 14, '{"features": ["search", "outreach"]}', 1, true),
            (gen_random_uuid(), 'Agency', 'agency', 'Team + analytics + priority — for agencies', 499.00, 14, '{"features": ["search", "outreach", "analytics", "team_members", "priority_support", "api_access", "custom_reports"]}', 2, true)
        """
    )


def downgrade() -> None:
    op.drop_table("invoice_line_items")
    op.drop_table("invoices")
    op.drop_table("subscription_events")
    op.drop_table("subscriptions")
    op.drop_table("plans")
