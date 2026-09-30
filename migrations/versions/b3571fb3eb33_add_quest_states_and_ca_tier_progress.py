"""add in-progress quests and combat achievement tier progress

Revision ID: b3571fb3eb33
Revises: 4b4e5621302d
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3571fb3eb33'
down_revision: Union[str, Sequence[str], None] = '4b4e5621302d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two new columns for Character Overview's quests/combat-
    achievements sections -- see both columns' own docstrings in
    app/models.py.

    in_progress_quests mirrors completed_quests' own shape (a JSONB
    list), so it gets the same NOT NULL + server_default treatment
    completed_quests itself would have needed had it been added after
    game_accounts already had rows (same reasoning clue_scroll_counts'
    own migration, 4b4e5621302d, gives for server_default over a plain
    default -- applies against existing rows immediately, no backfill
    needed since "nothing in progress" is exactly what an empty list
    already means).

    character_summary_combat_task_tier_completed stays nullable with no
    server_default, unlike the column above -- it follows every other
    character_summary_* column's own "null until the first sync that
    populates it" convention (see character_summary_combat_level and
    friends, none of which are NOT NULL either), not completed_quests/
    diary_tiers' "empty collection, not null" one, since an account
    that predates this column has no meaningful zero to backfill (a
    real 0 completed and "never synced" aren't the same thing here,
    unlike an empty in_progress_quests list which are)."""
    op.add_column(
        'game_accounts',
        sa.Column(
            'in_progress_quests',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'game_accounts',
        sa.Column(
            'character_summary_combat_task_tier_completed',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('game_accounts', 'character_summary_combat_task_tier_completed')
    op.drop_column('game_accounts', 'in_progress_quests')
