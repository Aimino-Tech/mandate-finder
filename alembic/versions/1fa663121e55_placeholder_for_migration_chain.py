"""placeholder for migration chain

Revision ID: 1fa663121e55
Revises: 001_initial
Create Date: 2026-06-11 09:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "1fa663121e55"
down_revision: str | Sequence[str] | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
