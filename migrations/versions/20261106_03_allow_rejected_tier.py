"""Allow rejected vacancy classification.

Revision ID: 20261106_03
Revises: 20261106_02
Create Date: 2026-11-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261106_03"
down_revision: str | None = "20261106_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_vacancies_tier", "vacancies", type_="check")
    op.create_check_constraint(
        "ck_vacancies_tier",
        "vacancies",
        "tier IN ('S', 'A', 'B', 'C', 'rejected')",
    )


def downgrade() -> None:
    op.execute("UPDATE vacancies SET tier = 'C' WHERE tier = 'rejected'")
    op.drop_constraint("ck_vacancies_tier", "vacancies", type_="check")
    op.create_check_constraint(
        "ck_vacancies_tier",
        "vacancies",
        "tier IN ('S', 'A', 'B', 'C')",
    )
