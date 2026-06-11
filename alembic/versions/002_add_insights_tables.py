"""Add company signals, watchlists, and activity events tables for AIM-1500."""
from typing import Sequence, Union

from alembic import op

revision: str = "002_add_insights_tables"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            competitor_count INTEGER NOT NULL DEFAULT 0,
            trend VARCHAR(20) NOT NULL DEFAULT 'stable',
            last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_company_signals_company ON company_signals(company_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS company_watchlists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            company_id UUID NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            notify_on_change BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_watchlists_user ON company_watchlists(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_watchlists_company ON company_watchlists(company_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS activity_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            company_id UUID NOT NULL,
            activity_type VARCHAR(50) NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_private BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_activity_events_user ON activity_events(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_activity_events_company ON activity_events(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_activity_events_company_private ON activity_events(company_id, is_private)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS activity_events")
    op.execute("DROP TABLE IF EXISTS company_watchlists")
    op.execute("DROP TABLE IF EXISTS company_signals")
