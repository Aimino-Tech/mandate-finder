"""Add A/B testing and reply detection tables

Revision ID: 002
Revises: eb697edb1fbb
Create Date: 2025-06-11 10:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002"
down_revision: str = "eb697edb1fbb"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "message_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("cta", sa.String(500), nullable=True),
        sa.Column("personalization_level", sa.String(50), server_default="low"),
        sa.Column("send_count", sa.Integer, server_default="0"),
        sa.Column("open_count", sa.Integer, server_default="0"),
        sa.Column("reply_count", sa.Integer, server_default="0"),
        sa.Column("meeting_count", sa.Integer, server_default="0"),
        sa.Column("is_control", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ab_tests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("control_variant_id", UUID(as_uuid=True), sa.ForeignKey("message_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("winning_variant_id", UUID(as_uuid=True), sa.ForeignKey("message_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("significance_threshold", sa.Float, server_default="0.05"),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "reply_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("message_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("handled_by_human", sa.Boolean, server_default="false"),
        sa.Column("raw_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("reply_events")
    op.drop_table("ab_tests")
    op.drop_table("message_variants")
