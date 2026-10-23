"""add game_accounts.diary_task_counts

Revision ID: a7d2f4c81e59
Revises: e1b6d3a94f27
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'a7d2f4c81e59'
down_revision: Union[str, Sequence[str], None] = 'e1b6d3a94f27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Per-area, per-tier achievement diary task counts -- see
    GameAccount.diary_task_counts in app/models.py. Existing rows start with
    an empty map until the plugin next syncs."""
    op.add_column(
        "game_accounts",
        sa.Column("diary_task_counts", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("game_accounts", "diary_task_counts")
