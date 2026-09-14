"""add potion storage items

Revision ID: 71ab8e8afc06
Revises: 6fe28e66f45d
Create Date: 2026-09-14 01:50:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '71ab8e8afc06'
down_revision: Union[str, Sequence[str], None] = '6fe28e66f45d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds potion_storage_items -- the same last-reported, full-replace
    snapshot shape as bank_items/inventory_items/equipment_items (see
    PotionStorageItem's docstring in app/models.py). This is what lets
    the RuneLite plugin report Player-Owned-House Potion Storage
    contents, closing the gap the old GearSlotItemIn.supplies flag used
    to paper over (a gear slot could be marked always-owned regardless
    of what was actually held, since the plugin had no way to see
    potions sitting in storage) -- that flag is removed in this same
    change, now that ownership can be checked for real."""
    op.create_table(
        "potion_storage_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_potion_storage_items_player_item"),
    )


def downgrade() -> None:
    op.drop_table("potion_storage_items")
