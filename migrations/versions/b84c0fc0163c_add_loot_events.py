"""add loot events

Revision ID: b84c0fc0163c
Revises: 4a943b230c24
Create Date: 2026-09-14 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = 'b84c0fc0163c'
down_revision: Union[str, Sequence[str], None] = '4a943b230c24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds loot_events -- an append-only log of kills/caskets/
    pickpockets (see LootEvent's docstring in app/models.py), the data
    source behind the new Loot Tracker feature (app/loot.py). Unlike
    every other synced-item table before this one, rows here are never
    deleted or replaced on sync -- event_id (unique per player) is what
    makes a resync of the same event safe instead of double-counting
    it."""
    op.create_table(
        "loot_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("combat_level", sa.Integer(), nullable=True),
        sa.Column("items", JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "event_id", name="uq_loot_events_player_event"),
    )
    op.create_index("ix_loot_events_player_id", "loot_events", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_loot_events_player_id", table_name="loot_events")
    op.drop_table("loot_events")
