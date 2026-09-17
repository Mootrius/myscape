"""rename costume_room_items to poh_items, add forestry_kit/master_scroll_book/seed_box

Revision ID: 3192ede99dfa
Revises: a7d2f6903c1e
Create Date: 2026-09-17T00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '3192ede99dfa'
down_revision: Union[str, Sequence[str], None] = 'a7d2f6903c1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two independent changes, bundled since they landed in the same
    request:

    1. Rename costume_room_items -> poh_items (and its unique
       constraint) to match the "PoH" label Storages Viewer's
       location filter now groups this storage under -- see PohItem's
       docstring in app/models.py. A rename, not a drop/recreate, so
       any already-synced rows survive.

    2. Add three new item-source tables -- forestry_kit_items (real,
       confirmed InventoryID.FORESTRY_KIT = 814), seed_box_items (real,
       confirmed InventoryID.SEED_BOX = 573), and
       master_scroll_book_items (no confirmed container id yet -- see
       MasterScrollBookItem's docstring in app/models.py; this table is
       ready to receive rows once the plugin's diagnostic logging
       finds the real one, but may sit empty for a while)."""
    op.rename_table("costume_room_items", "poh_items")
    op.execute(
        "ALTER TABLE poh_items "
        "RENAME CONSTRAINT uq_costume_room_items_player_item "
        "TO uq_poh_items_player_item"
    )

    op.create_table(
        "forestry_kit_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_forestry_kit_items_player_item"),
    )
    op.create_table(
        "master_scroll_book_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_master_scroll_book_items_player_item"),
    )
    op.create_table(
        "seed_box_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_seed_box_items_player_item"),
    )


def downgrade() -> None:
    op.drop_table("seed_box_items")
    op.drop_table("master_scroll_book_items")
    op.drop_table("forestry_kit_items")

    op.execute(
        "ALTER TABLE poh_items "
        "RENAME CONSTRAINT uq_poh_items_player_item "
        "TO uq_costume_room_items_player_item"
    )
    op.rename_table("poh_items", "costume_room_items")
