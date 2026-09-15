"""add goal tracking state (skills, quests, diaries, seed vault)

Revision ID: f09e733c7c88
Revises: 422daa0bff65
Create Date: 2026-09-15 06:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = 'f09e733c7c88'
down_revision: Union[str, Sequence[str], None] = '422daa0bff65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Everything Mindmaps' goal-node auto-completion (see
    evaluate_completion in app/mindmaps.py) needs from the player that
    nothing existing already covers:

    - seed_vault_items: the same last-reported, full-replace snapshot
      shape as bank_items/inventory_items/equipment_items/
      potion_storage_items/rune_pouch_items (see those tables'
      docstrings in app/models.py) -- one more source _build_owned_pools
      in app/purchase_goals.py folds an item-goal node's target item
      into, alongside everything else the player owns.
    - players.skills/completed_quests/diary_tiers: unlike the item
      sources above, each of these is always read and written as one
      whole snapshot rather than many independent rows (a player has
      exactly one current level+xp per skill, one list of completed
      quests, one highest diary tier per area), so a JSONB column
      directly on Player fits the same way GearSetup.equipment/
      inventory already does, rather than three more single-purpose
      tables. See Player's docstring in app/models.py for the shape
      each holds."""
    op.create_table(
        "seed_vault_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "item_id", name="uq_seed_vault_items_player_item"),
    )
    op.add_column(
        "players",
        sa.Column("skills", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "players",
        sa.Column("completed_quests", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "players",
        sa.Column("diary_tiers", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("players", "diary_tiers")
    op.drop_column("players", "completed_quests")
    op.drop_column("players", "skills")
    op.drop_table("seed_vault_items")
