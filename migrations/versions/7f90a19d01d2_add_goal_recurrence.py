"""add goal recurrence

Revision ID: 7f90a19d01d2
Revises: 271e77f0e2d4
Create Date: 2026-09-21 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f90a19d01d2'
down_revision: Union[str, Sequence[str], None] = '271e77f0e2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the columns behind a recurring ("every 1 WEEK", etc.) "kc"
    or "skill" goal -- see Goal's own docstring in app/models.py for
    what each one means and app.goals.maybe_roll_recurring_period for
    the rollover logic that reads/writes recur_period_start and
    recur_baseline_value on every list read. is_recurring defaults
    false so every existing goal keeps behaving exactly as it already
    does (a lifetime-total target, never rolled over)."""
    op.add_column("goals", sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("goals", sa.Column("recur_interval", sa.Integer(), nullable=True))
    op.add_column("goals", sa.Column("recur_unit", sa.String(), nullable=True))
    op.add_column("goals", sa.Column("recur_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goals", sa.Column("recur_baseline_value", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("goals", "recur_baseline_value")
    op.drop_column("goals", "recur_period_start")
    op.drop_column("goals", "recur_unit")
    op.drop_column("goals", "recur_interval")
    op.drop_column("goals", "is_recurring")
