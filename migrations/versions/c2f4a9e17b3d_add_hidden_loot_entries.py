"""add hidden loot entries

Revision ID: c2f4a9e17b3d
Revises: 8d8412752a5b
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'c2f4a9e17b3d'
down_revision: Union[str, Sequence[str], None] = '8d8412752a5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """hidden_loot_entries -- Loot Tracker's "hide this NPC/item" marker
    (see HiddenLootEntry's own docstring in app/models.py). One row per
    (player, kind, key) hidden; deleting the row unhides it. kind is
    "npc" or "item"; key is the same lowercased identity string
    loot_hide_key computes in app/loot.py."""
    op.create_table(
        "hidden_loot_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "kind", "key", name="uq_hidden_loot_entries_player_kind_key"),
    )
    op.create_index(
        "ix_hidden_loot_entries_player_id", "hidden_loot_entries", ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_hidden_loot_entries_player_id", table_name="hidden_loot_entries")
    op.drop_table("hidden_loot_entries")
