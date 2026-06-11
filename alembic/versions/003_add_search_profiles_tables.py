"""Add search_profiles and profile_matches tables.

Revision ID: 003
Revises: eb697edb1fbb
Create Date: 2026-06-11 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "eb697edb1fbb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_profiles",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("radius_km", sa.Integer(), nullable=True),
        sa.Column("industries", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("employment_type", sa.String(length=100), nullable=True),
        sa.Column("exclusions", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_on_score_above", sa.Float(), nullable=False, server_default=sa.text("0.8")),
        sa.Column("notify_channels", sa.String(length=255), nullable=False, server_default=sa.text("'email'")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_search_profiles_user_id"), "search_profiles", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_search_profiles_is_active"), "search_profiles", ["is_active"], unique=False
    )

    op.create_table(
        "profile_matches",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_posting_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("user_feedback", sa.String(length=50), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["profile_id"], ["search_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_profile_matches_profile_id"), "profile_matches", ["profile_id"], unique=False
    )
    op.create_index(
        op.f("ix_profile_matches_job_posting_id"), "profile_matches", ["job_posting_id"], unique=False
    )
    op.create_index(
        op.f("ix_profile_matches_score"), "profile_matches", ["score"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_matches_score"), table_name="profile_matches")
    op.drop_index(op.f("ix_profile_matches_job_posting_id"), table_name="profile_matches")
    op.drop_index(op.f("ix_profile_matches_profile_id"), table_name="profile_matches")
    op.drop_table("profile_matches")
    op.drop_index(op.f("ix_search_profiles_is_active"), table_name="search_profiles")
    op.drop_index(op.f("ix_search_profiles_user_id"), table_name="search_profiles")
    op.drop_table("search_profiles")
