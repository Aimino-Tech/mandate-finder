"""Add billing tables: plans, subscriptions, invoices."""
from typing import Sequence, Union

from alembic import op

revision: str = "002_billing_tables"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            tier VARCHAR(50) NOT NULL,
            price_monthly_eur INTEGER NOT NULL,
            features JSONB NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plans_tier ON plans(tier)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            plan_id UUID NOT NULL REFERENCES plans(id),
            stripe_subscription_id VARCHAR(255) UNIQUE,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            trial_end_at TIMESTAMPTZ,
            current_period_start TIMESTAMPTZ,
            current_period_end TIMESTAMPTZ,
            canceled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscriptions_status ON subscriptions(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subscription_id UUID NOT NULL REFERENCES subscriptions(id),
            stripe_invoice_id VARCHAR(255) UNIQUE,
            amount_eur INTEGER NOT NULL,
            vat_percentage INTEGER NOT NULL DEFAULT 19,
            vat_amount INTEGER NOT NULL,
            total_eur INTEGER NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            pdf_url VARCHAR(512),
            paid_at TIMESTAMPTZ,
            period_start TIMESTAMPTZ,
            period_end TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoices_subscription_id ON invoices(subscription_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status)")

    # Add stripe_customer_id to users table
    op.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_stripe_customer_id ON users(stripe_customer_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_stripe_customer_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS stripe_customer_id")
    op.execute("DROP TABLE IF EXISTS invoices")
    op.execute("DROP TABLE IF EXISTS subscriptions")
    op.execute("DROP TABLE IF EXISTS plans")
