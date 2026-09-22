"""rename goal baseline column and allow one time gain goals

Revision ID: e5fcc1ed7029
Revises: b7eac088f286
Create Date: 2026-09-22 05:55:37.027463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5fcc1ed7029'
down_revision: Union[str, Sequence[str], None] = 'b7eac088f286'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Renames goals.recur_baseline_value to goals.baseline_value -- a
    plain rename (op.alter_column, not a drop+add), so every recurring
    goal's own already-captured baseline survives this untouched. The
    column itself needs no schema change (still Integer, still
    nullable) -- what changed is what it's FOR: this same column now
    also holds a one-time "GAIN"-mode kc/xp-metric-skill goal's own
    baseline (captured once at creation, see create_goal in
    app/main.py), not just a recurring goal's period-relative one, now
    that current_value() (app/goals.py) reads it purely off "is this
    null" rather than goal.is_recurring. See Goal.baseline_value's own
    docstring in app/models.py for the full reasoning. No data
    migration needed beyond the rename itself -- every existing goal's
    baseline (recurring) or lack of one (everything else, all
    REACH-mode before this shipped) means exactly the same thing under
    the new name it already meant under the old one."""
    op.alter_column("goals", "recur_baseline_value", new_column_name="baseline_value")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("goals", "baseline_value", new_column_name="recur_baseline_value")
