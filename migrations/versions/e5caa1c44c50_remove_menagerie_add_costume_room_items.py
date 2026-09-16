"""remove menagerie, add costume room storage items

Revision ID: e5caa1c44c50
Revises: 1e09bad3102c
Create Date: 2026-09-16T23:18:52.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'e5caa1c44c50'
down_revision: Union[str, Sequence[str], None] = '1e09bad3102c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drops menagerie_items (Menagerie sync was removed -- pets are
    the player's own, not a real separate "possession" the way the
    other storages are, and tracking them here added more confusion
    than value) and adds six new owned-item sources for Possessions
    Monitoring, same last-reported full-replace snapshot shape as
    every other item table (see each new *Item class's own docstring
    in app/models.py):

    - magic_wardrobe_items: the Costume Room's Magic Wardrobe
      (InventoryID.POH_COSTUME_ROOM_MAGIC_WARDROBE_INV).
    - armour_case_items: the Costume Room's Armour Case (InventoryID.
      POH_COSTUME_ROOM_ARMOUR_INV).
    - fancy_dress_box_items: the Costume Room's Fancy Dress Box
      (InventoryID.POH_COSTUME_ROOM_AME_INV).
    - toy_box_items: the Costume Room's Toy Box (InventoryID.
      POH_COSTUME_ROOM_HOLIDAY_ITEMS_INV).
    - treasure_chest_items: the Costume Room's Treasure Chest, merged
      client-side from all six Treasure Trail difficulty tiers'
      ItemContainers (InventoryID.POH_COSTUME_ROOM_TREASURE_TRAIL_1_INV
      through _3_INV and _1A_INV through _3A_INV).
    - magic_cape_rack_items: the Costume Room's Cape Rack, merged
      client-side from both of its widget pages (InventoryID.
      POH_COSTUME_ROOM_CAPES_INV and _CAPES_INV_PAGE2).

    players.storage_synced_at (added back in 3e81d103586c) already
    covers any storage key stamped into it -- the six new keys just
    join "bank"/"seed_vault"/"tackle_box"/etc. there, and "menagerie"
    simply stops being stamped, with no schema change of its own
    needed either way."""
    op.drop_table("menagerie_items")

    op.create_table(
        "magic_wardrobe_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_magic_wardrobe_items_player_item"),
    )
    op.create_table(
        "armour_case_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_armour_case_items_player_item"),
    )
    op.create_table(
        "fancy_dress_box_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_fancy_dress_box_items_player_item"),
    )
    op.create_table(
        "toy_box_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_toy_box_items_player_item"),
    )
    op.create_table(
        "treasure_chest_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_treasure_chest_items_player_item"),
    )
    op.create_table(
        "magic_cape_rack_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_magic_cape_rack_items_player_item"),
    )


def downgrade() -> None:
    op.drop_table("magic_cape_rack_items")
    op.drop_table("treasure_chest_items")
    op.drop_table("toy_box_items")
    op.drop_table("fancy_dress_box_items")
    op.drop_table("armour_case_items")
    op.drop_table("magic_wardrobe_items")

    op.create_table(
        "menagerie_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_menagerie_items_player_item"),
    )
