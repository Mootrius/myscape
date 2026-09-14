"""add rune pouch items

Revision ID: 4a943b230c24
Revises: dfd50a36bfd5
Create Date: 2026-09-14 06:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '4a943b230c24'
down_revision: Union[str, Sequence[str], None] = 'dfd50a36bfd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds rune_pouch_items -- the same last-reported, full-replace
    snapshot shape as bank_items/inventory_items/equipment_items/
    potion_storage_items (see RunePouchItem's docstring in
    app/models.py). This is what lets the RuneLite plugin report a Rune
    Pouch's contents: RuneLite's normal inventory scan only ever sees
    the pouch itself as a single item, not the runes stored inside it,
    so without this table those runes were invisible to Purchase Goals
    entirely -- a setup needing (for example) fire runes kept listing
    them as still to buy even while a full pouch of them sat in the
    player's own inventory."""
    op.create_table(
        "rune_pouch_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_rune_pouch_items_player_item"),
    )


def downgrade() -> None:
    op.drop_table("rune_pouch_items")
