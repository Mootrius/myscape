"""add menagerie and tackle box items

Revision ID: 1e09bad3102c
Revises: c2f4a9e17b3d
Create Date: 2026-09-16T00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '1e09bad3102c'
down_revision: Union[str, Sequence[str], None] = 'c2f4a9e17b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two more owned-item sources for Storages Viewer, same
    last-reported full-replace snapshot shape as every other item table
    (see MenagerieItem/TackleBoxItem's own docstrings in app/models.py):

    - menagerie_items: the Player-Owned-House Menagerie's stored pets
      (InventoryID.POH_MENAGERIE_PETS).
    - tackle_box_items: a Tackle Box's contents (InventoryID.
      TACKLE_BOX).

    players.storage_synced_at (added back in 3e81d103586c) already
    covers any storage key stamped into it -- "menagerie" and
    "tackle_box" just join "bank"/"seed_vault"/"looting_bag"/etc. there
    with no schema change of its own needed."""
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
    op.create_table(
        "tackle_box_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_tackle_box_items_player_item"),
    )


def downgrade() -> None:
    op.drop_table("tackle_box_items")
    op.drop_table("menagerie_items")
