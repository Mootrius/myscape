"""add huntsmans kit and boat cargo items

Revision ID: 5842ebde3965
Revises: ac7e92357d68
Create Date: 2026-09-19T03:36:09.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '5842ebde3965'
down_revision: Union[str, Sequence[str], None] = 'ac7e92357d68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two more owned-item sources for Storages Viewer, same
    last-reported full-replace snapshot shape as every other item table
    (see HuntsmansKitItem/BoatCargoItem's own docstrings in
    app/models.py):

    - huntsmans_kit_items: a Huntsman's Kit's contents (InventoryID.
      HUNTSMANS_KIT) -- grouped under the "PORTABLE" location on
      Storages Viewer, same as Tackle Box/Forestry Kit/Seed Box.
    - boat_cargo_items: one of a player's up to five independently-
      owned boats' cargo hold contents (InventoryID.
      SAILING_BOAT_1_CARGOHOLD through SAILING_BOAT_5_CARGOHOLD) --
      its own new "BOATS" location on Storages Viewer, right after
      PoH. Unlike every other item table here, this one carries a
      `slot` column (1-5, which boat) so a sync of one boat can
      delete-and-replace just that boat's own rows without touching
      what's already known about the other four -- see the model's
      own docstring for why that matters (boats don't share contents
      the way PoH's six furniture pieces turned out to).

    players.storage_synced_at (added back in 3e81d103586c) already
    covers any storage key stamped into it -- "huntsmans_kit" and
    "boat_cargo" just join "bank"/"seed_vault"/"looting_bag"/etc.
    there with no schema change of its own needed."""
    op.create_table(
        "huntsmans_kit_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_huntsmans_kit_items_player_item"),
    )
    op.create_table(
        "boat_cargo_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "slot", "item_id", name="uq_boat_cargo_items_player_slot_item"),
    )


def downgrade() -> None:
    op.drop_table("boat_cargo_items")
    op.drop_table("huntsmans_kit_items")
