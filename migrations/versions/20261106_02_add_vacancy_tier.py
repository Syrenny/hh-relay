"""Add vacancy tier.

Revision ID: 20261106_02
Revises: 20261102_01
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261106_02"
down_revision: str | None = "20261102_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vacancies", sa.Column("tier", sa.Text()))
    op.execute(
        """
        UPDATE vacancies
        SET tier = CASE rating
            WHEN 'strong' THEN 'S'
            WHEN 'debatable' THEN 'B'
            WHEN 'skip' THEN 'C'
        END
        """
    )
    op.create_check_constraint(
        "ck_vacancies_tier",
        "vacancies",
        "tier IN ('S', 'A', 'B', 'C')",
    )
    op.create_index(
        "vacancies_tier_published_idx",
        "vacancies",
        ["tier", sa.text("published_at DESC")],
    )
    op.drop_constraint("ck_vacancies_rating", "vacancies", type_="check")
    op.drop_column("vacancies", "rating")


def downgrade() -> None:
    op.add_column("vacancies", sa.Column("rating", sa.Text()))
    op.execute(
        """
        UPDATE vacancies
        SET rating = CASE tier
            WHEN 'S' THEN 'strong'
            WHEN 'A' THEN 'strong'
            WHEN 'B' THEN 'debatable'
            WHEN 'C' THEN 'skip'
        END
        """
    )
    op.create_check_constraint(
        "ck_vacancies_rating",
        "vacancies",
        "rating IN ('strong', 'debatable', 'skip')",
    )
    op.drop_index("vacancies_tier_published_idx", table_name="vacancies")
    op.drop_constraint("ck_vacancies_tier", "vacancies", type_="check")
    op.drop_column("vacancies", "tier")
