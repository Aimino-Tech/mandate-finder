"""add job_postings table

Revision ID: eb697edb1fbb
Revises: 1fa663121e55
Create Date: 2026-06-11 09:51:16.941610

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

from alembic import op

revision: str = "eb697edb1fbb"
down_revision: str | Sequence[str] | None = "1fa663121e55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_postings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("company_domain", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("skills", sqlite.JSON(), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("role_category", sa.String(length=64), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("raw", sqlite.JSON(), nullable=True),
        sa.Column("pipeline_run", sa.String(length=36), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_job_postings_source_id"), "job_postings", ["source_id"], unique=False)
    op.create_index(op.f("ix_job_postings_source"), "job_postings", ["source"], unique=False)
    op.create_index(op.f("ix_job_postings_company"), "job_postings", ["company"], unique=False)
    op.create_index(op.f("ix_job_postings_pipeline_run"), "job_postings", ["pipeline_run"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_postings_pipeline_run"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_company"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_source"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_source_id"), table_name="job_postings")
    op.drop_table("job_postings")
