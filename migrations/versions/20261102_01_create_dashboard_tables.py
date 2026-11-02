"""Create dashboard tables.

Revision ID: 20261102_01
Revises:
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261102_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vacancies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("employer", sa.Text()),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("salary", postgresql.JSONB()),
        sa.Column("area", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("rating", sa.Text()),
        sa.Column("rationale", sa.Text()),
        sa.Column("requirements", postgresql.JSONB()),
        sa.Column("warnings", postgresql.JSONB()),
        sa.Column("user_status", sa.Text(), nullable=False, server_default="new"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("emailed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "rating IN ('strong', 'debatable', 'skip')",
            name="ck_vacancies_rating",
        ),
        sa.CheckConstraint(
            "user_status IN "
            "('new', 'interesting', 'applied', 'not_suitable', 'archived')",
            name="ck_vacancies_user_status",
        ),
    )
    op.create_index(
        "vacancies_status_published_idx",
        "vacancies",
        ["user_status", sa.text("published_at DESC")],
    )
    op.create_table(
        "cover_letters",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "vacancy_id",
            sa.Text(),
            sa.ForeignKey("vacancies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("letter", sa.Text()),
        sa.Column("warning", sa.Text()),
        sa.Column("special_requirement", sa.Text()),
        sa.Column("question", sa.Text()),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "monitor_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emailed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("monitor_runs")
    op.drop_table("cover_letters")
    op.drop_index("vacancies_status_published_idx", table_name="vacancies")
    op.drop_table("vacancies")
