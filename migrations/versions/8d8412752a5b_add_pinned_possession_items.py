"""add pinned possession items

Revision ID: 8d8412752a5b
Revises: 3e81d103586c
Create Date: 2026-09-18 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '8d8412752a5b'
down_revision: Union[str, Sequence[str], None] = '3e81d103586c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """pinned_possession_items -- Possessions Monitoring section 3's
    "pin to the top" marker (see PinnedPossessionItem's own docstring
    in app/models.py). One row per (player, item_id) pinned; deleting
    the row unpins it."""
    op.create_table(
        "pinned_possession_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_pinned_possession_items_player_item"),
    )
    op.create_index(
        "ix_pinned_possession_items_player_id", "pinned_possession_items", ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pinned_possession_items_player_id", table_name="pinned_possession_items")
    op.drop_table("pinned_possession_items")
