"""add possessions monitoring (looting bag items, storage sync status, trackers)

Revision ID: 3e81d103586c
Revises: f09e733c7c88
Create Date: 2026-09-15 23:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '3e81d103586c'
down_revision: Union[str, Sequence[str], None] = 'f09e733c7c88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Everything the new Possessions Monitoring app needs (see
    app/possessions.py and render_possessions in app/pages.py):

    - looting_bag_items: the same last-reported, full-replace snapshot
      shape as bank_items/inventory_items/.../seed_vault_items (see
      those tables' docstrings in app/models.py) -- one more owned-item
      source, and the seventh storage the side panel's new Status
      section reports on.
    - players.storage_synced_at: a small JSONB map stamped by every one
      of the seven sync endpoints (see that column's own docstring on
      Player in app/models.py) -- what the Status section actually
      reads, since an item table's own updated_at can't tell "synced
      empty" apart from "never synced".
    - possession_trackers: the minimum/maximum item trackers behind
      Possessions Monitoring's first two sections (see
      PossessionTracker's own docstring in app/models.py)."""
    op.create_table(
        "looting_bag_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_looting_bag_items_player_item"),
    )
    op.add_column(
        "players",
        sa.Column("storage_synced_at", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "possession_trackers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "kind", "item_id", name="uq_possession_trackers_player_kind_item"),
    )
    op.create_index(
        "ix_possession_trackers_player_id", "possession_trackers", ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_possession_trackers_player_id", table_name="possession_trackers")
    op.drop_table("possession_trackers")
    op.drop_column("players", "storage_synced_at")
    op.drop_table("looting_bag_items")
