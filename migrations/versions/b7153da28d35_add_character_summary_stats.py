"""add character summary stats

Revision ID: b7153da28d35
Revises: c3f7a2e04d9b
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7153da28d35'
down_revision: Union[str, Sequence[str], None] = 'c3f7a2e04d9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('game_accounts', sa.Column('character_summary_combat_level', sa.Float(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_total_level', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_total_xp', sa.BigInteger(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_quests_completed', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_quests_total', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_achievements_completed', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_achievements_total', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_combat_tasks_completed', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_combat_tasks_total', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_collections_completed', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_collections_total', sa.Integer(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_summary_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('game_accounts', 'character_summary_synced_at')
    op.drop_column('game_accounts', 'character_summary_collections_total')
    op.drop_column('game_accounts', 'character_summary_collections_completed')
    op.drop_column('game_accounts', 'character_summary_combat_tasks_total')
    op.drop_column('game_accounts', 'character_summary_combat_tasks_completed')
    op.drop_column('game_accounts', 'character_summary_achievements_total')
    op.drop_column('game_accounts', 'character_summary_achievements_completed')
    op.drop_column('game_accounts', 'character_summary_quests_total')
    op.drop_column('game_accounts', 'character_summary_quests_completed')
    op.drop_column('game_accounts', 'character_summary_total_xp')
    op.drop_column('game_accounts', 'character_summary_total_level')
    op.drop_column('game_accounts', 'character_summary_combat_level')
