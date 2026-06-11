"""Initial schema: users, organizations, members, audit logs."""
from typing import Sequence, Union

from alembic import op

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            propelauth_user_id VARCHAR(255) UNIQUE,
            user_type VARCHAR(50) NOT NULL DEFAULT 'trial',
            information JSONB NOT NULL DEFAULT '{}',
            settings JSONB NOT NULL DEFAULT '{}',
            organization_id UUID REFERENCES organizations(id),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS organization_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_org_members_org ON organization_members(organization_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_org_members_user_org ON organization_members(user_id, organization_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID,
            organization_id UUID,
            action VARCHAR(255) NOT NULL,
            resource_type VARCHAR(255) NOT NULL,
            resource_id VARCHAR(255),
            details JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_user ON audit_logs(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_org ON audit_logs(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS organization_members")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS organizations")
