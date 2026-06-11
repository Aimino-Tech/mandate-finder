"""Add BA-specific columns to job_postings table.

This migration adds the fields needed for Bundesagentur für Arbeit
integration while preserving backward compatibility with the
existing pipeline schema.

Revision ID: 2a3b4c5d6e7f
Revises: eb697edb1fbb
Create Date: 2026-06-11 14:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "2a3b4c5d6e7f"
down_revision: Union[str, Sequence[str], None] = "eb697edb1fbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add BA integration columns and update column types."""
    # Add new columns for BA integration
    op.add_column("job_postings", sa.Column("location_city", sa.String(255), nullable=True))
    op.add_column("job_postings", sa.Column("location_state", sa.String(255), nullable=True))
    op.add_column("job_postings", sa.Column("occupation_code", sa.String(20), nullable=True))
    op.add_column("job_postings", sa.Column("salary_min", sa.Float(), nullable=True))
    op.add_column("job_postings", sa.Column("salary_max", sa.Float(), nullable=True))
    op.add_column("job_postings", sa.Column("salary_currency", sa.String(3), nullable=True))
    op.add_column("job_postings", sa.Column("employment_type", sa.String(50), nullable=True))

    # Add index on source for faster filtering
    op.create_index(
        op.f("ix_job_postings_source_ba"),
        "job_postings",
        ["source"],
        unique=False,
    )

    # Add index on source_job_id for dedup
    op.create_index(
        op.f("ix_job_postings_source_id_ba"),
        "job_postings",
        ["source_id"],
        unique=False,
    )

    # Create composite index for common BA queries
    op.create_index(
        op.f("ix_job_postings_source_company_ba"),
        "job_postings",
        ["source", "company"],
        unique=False,
    )


def downgrade() -> None:
    """Remove BA-specific columns and indexes."""
    op.drop_index(op.f("ix_job_postings_source_company_ba"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_source_id_ba"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_source_ba"), table_name="job_postings")
    op.drop_column("job_postings", "employment_type")
    op.drop_column("job_postings", "salary_currency")
    op.drop_column("job_postings", "salary_max")
    op.drop_column("job_postings", "salary_min")
    op.drop_column("job_postings", "occupation_code")
    op.drop_column("job_postings", "location_state")
    op.drop_column("job_postings", "location_city")
