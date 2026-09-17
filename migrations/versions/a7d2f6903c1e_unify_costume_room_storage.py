"""unify the six costume room tables into one costume_room_items

Revision ID: a7d2f6903c1e
Revises: e5caa1c44c50
Create Date: 2026-09-17T00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'a7d2f6903c1e'
down_revision: Union[str, Sequence[str], None] = 'e5caa1c44c50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The six tables e5caa1c44c50 added (magic_wardrobe_items,
    armour_case_items, fancy_dress_box_items, toy_box_items,
    treasure_chest_items, magic_cape_rack_items) were modeled on the six
    named InventoryID.POH_COSTUME_ROOM_* constants RuneLite exposes --
    but live testing (opening each piece of furniture and logging which
    ItemContainer actually fires) found every one of them fires
    ItemContainerChanged on the exact same container id (33405, not any
    of those six constants), with identical contents regardless of
    which piece was opened. That's why nothing ever synced: the plugin
    was listening for containers that never fire. Jagex's newer,
    consolidated Costume Room interface (InterfaceID.POH_COSTUMES)
    reads from one unified store, not six -- see CostumeRoomItem's
    docstring in app/models.py. This drops the six per-piece tables and
    replaces them with costume_room_items, one row per owned item
    across the whole room."""
    op.drop_table("magic_wardrobe_items")
    op.drop_table("armour_case_items")
    op.drop_table("fancy_dress_box_items")
    op.drop_table("toy_box_items")
    op.drop_table("treasure_chest_items")
    op.drop_table("magic_cape_rack_items")

    op.create_table(
        "costume_room_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_costume_room_items_player_item"),
    )


def downgrade() -> None:
    op.drop_table("costume_room_items")

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
