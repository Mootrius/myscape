"""add collection log items

Revision ID: ae0e6a29837c
Revises: 0c5261ac64e7
Create Date: 2026-09-30 02:36:30.266587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ae0e6a29837c'
down_revision: Union[str, Sequence[str], None] = '0c5261ac64e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The per-item collection log obtained/quantity snapshot -- see
    GameAccount.collection_log_items' own comment in app/models.py.

    server_default on collection_log_items so this NOT NULL column can
    apply against existing game_accounts rows without backfilling each
    one first, same reasoning (and same '{}'::jsonb value) as
    99784a953617's boss_kill_counts column before it."""
    op.add_column(
        'game_accounts',
        sa.Column(
            'collection_log_items',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column('game_accounts', sa.Column('collection_log_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('game_accounts', 'collection_log_synced_at')
    op.drop_column('game_accounts', 'collection_log_items')
