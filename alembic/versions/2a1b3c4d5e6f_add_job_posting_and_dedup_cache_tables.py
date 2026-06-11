"""Add JobPosting and DedupCache tables (AIM-1489)

Revision ID: 2a1b3c4d5e6f
Revises: 001_initial
Create Date: 2026-06-11 11:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "2a1b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the legacy job_postings table if it exists (from broken migration chain)
    op.execute("DROP TABLE IF EXISTS job_postings CASCADE")
    op.execute("DROP TABLE IF EXISTS dedup_cache CASCADE")

    # --- job_postings ---
    op.create_table(
        "job_postings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("normalized_title", sa.String(length=512), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("salary_currency", sa.String(length=10), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("employment_type", sa.String(length=32), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("occupation_code", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("fingerprint_md5", sa.String(length=32), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_job_postings_source"), "job_postings", ["source"], unique=False)
    op.create_index(op.f("ix_job_postings_fingerprint_md5"), "job_postings", ["fingerprint_md5"], unique=False)

    # --- dedup_cache ---
    op.create_table(
        "dedup_cache",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint_md5", sa.String(length=32), nullable=False),
        sa.Column("source_job_ids", sa.JSON(), nullable=False),
        sa.Column("merged_job_posting_id", sa.String(length=36), nullable=True),
        sa.Column("dedup_level", sa.String(length=32), nullable=False, server_default=sa.text("'NEW'")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_dedup_cache_fingerprint_md5"),
        "dedup_cache",
        ["fingerprint_md5"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_dedup_cache_merged_job",
        "dedup_cache",
        "job_postings",
        ["merged_job_posting_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_table("dedup_cache")
    op.drop_table("job_postings")
