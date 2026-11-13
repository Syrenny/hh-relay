"""Add deterministic vacancy search settings.

Revision ID: 20261113_04
Revises: 20261106_03
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261113_04"
down_revision: str | None = "20261106_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("queries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("experiences", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_search_settings_singleton"),
        sa.CheckConstraint(
            "jsonb_typeof(queries) = 'array' AND jsonb_array_length(queries) > 0",
            name="ck_search_settings_queries",
        ),
        sa.CheckConstraint(
            "cardinality(experiences) > 0 AND experiences <@ "
            "ARRAY['noExperience', 'between1And3']::text[]",
            name="ck_search_settings_experiences",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO search_settings (id, queries, experiences)
        VALUES (
            1,
            '["Python backend", "Backend Python", "Python developer",
              "Python разработчик", "Junior Python", "Django developer",
              "FastAPI"]'::jsonb,
            ARRAY['noExperience', 'between1And3']
        )
        """
    )


def downgrade() -> None:
    op.drop_table("search_settings")
