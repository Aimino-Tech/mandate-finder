"""Add scrap_sources and scrap_runs tables for Hermes job board scraping.

Revision ID: 002_add_scrap_tables
Revises: eb697edb1fbb
Create Date: 2026-06-11 11:44:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_add_scrap_tables"
down_revision: Union[str, Sequence[str], None] = "eb697edb1fbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scrap_sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) NOT NULL UNIQUE,
            base_url VARCHAR(500) NOT NULL,
            rate_limit_per_minute INTEGER NOT NULL DEFAULT 30,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            health_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
            last_health_check TIMESTAMPTZ,
            config JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scrap_sources_name ON scrap_sources(name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scrap_sources_active ON scrap_sources(is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS scrap_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id UUID NOT NULL REFERENCES scrap_sources(id),
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            jobs_found INTEGER NOT NULL DEFAULT 0,
            jobs_new INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            error_details JSONB,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scrap_runs_source ON scrap_runs(source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scrap_runs_status ON scrap_runs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scrap_runs_started ON scrap_runs(started_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scrap_runs")
    op.execute("DROP TABLE IF EXISTS scrap_sources")
