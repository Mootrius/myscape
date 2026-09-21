"""add goals

Revision ID: 10baf11afbda
Revises: 65e934c8e549
Create Date: 2026-09-21 05:05:00.968207

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '10baf11afbda'
down_revision: Union[str, Sequence[str], None] = '65e934c8e549'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds goals -- the redesigned Goal Tracking page's own flat,
    per-account goal list (a boss kill-count target, a skill level/xp
    target, or an item quantity target). One row per goal, unlike
    mindmaps' single `nodes` JSONB blob -- see Goal's docstring in
    app/models.py for why a goal here earns a normal table instead."""
    op.create_table(
        "goals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("game_account_id", UUID(as_uuid=True), sa.ForeignKey("game_accounts.id"), nullable=False),
        sa.Column("goal_type", sa.String(), nullable=False),
        sa.Column("target_name", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=True),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("goals")
