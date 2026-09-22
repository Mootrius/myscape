"""add goal sort order and account sort mode

Revision ID: b7eac088f286
Revises: 7f90a19d01d2
Create Date: 2026-09-22 04:31:49.796070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7eac088f286'
down_revision: Union[str, Sequence[str], None] = '7f90a19d01d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the two columns behind Goal Tracking's own sort tabs (see
    GameAccount.goal_sort_mode and Goal.sort_order's own docstrings in
    app/models.py). goal_sort_mode's server_default backfills every
    existing account to "alphabetical" -- the same order the goal list
    always sorted by before this column existed, so nobody's list
    silently reorders itself the moment this ships. sort_order stays
    plain NULL for every existing goal (nothing's ever been dragged
    yet), same as a freshly created one -- app.goals/the client's own
    sortGoals both already fall back to created_at for a null
    sort_order, so this needs no backfill of its own."""
    op.add_column(
        "game_accounts",
        sa.Column("goal_sort_mode", sa.String(), nullable=False, server_default="alphabetical"),
    )
    op.add_column("goals", sa.Column("sort_order", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("goals", "sort_order")
    op.drop_column("game_accounts", "goal_sort_mode")
