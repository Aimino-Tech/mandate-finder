"""add CRM, metric, and alert tables

Revision ID: 300529638d64
Revises: 1fa663121e55
Create Date: 2026-06-11 01:02:05.021026

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision: str = "300529638d64"
down_revision: Union[str, Sequence[str], None] = "1fa663121e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("condition", sa.String(length=20), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("slack_webhook_url", sa.String(length=500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alert_configs_metric_type"), "alert_configs", ["metric_type"], unique=False)
    op.create_table(
        "crm_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("crm_type", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.String(length=50), nullable=True),
        sa.Column("instance_url", sa.String(length=512), nullable=True),
        sa.Column("field_mapping", sqlite.JSON(), nullable=False),
        sa.Column("auto_sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("synced_lead_ids", sqlite.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "metric_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("labels", sqlite.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metric_events_metric_type"), "metric_events", ["metric_type"], unique=False)
    op.create_index(op.f("ix_metric_events_recorded_at"), "metric_events", ["recorded_at"], unique=False)
    op.create_table(
        "crm_sync_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=255), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("contact_id", sa.String(length=255), nullable=True),
        sa.Column("deal_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lead_snapshot", sqlite.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["crm_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("crm_sync_logs")
    op.drop_index(op.f("ix_metric_events_recorded_at"), table_name="metric_events")
    op.drop_index(op.f("ix_metric_events_metric_type"), table_name="metric_events")
    op.drop_table("metric_events")
    op.drop_table("crm_connections")
    op.drop_index(op.f("ix_alert_configs_metric_type"), table_name="alert_configs")
    op.drop_table("alert_configs")
