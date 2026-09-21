"""add boss kill counts updated at

Revision ID: 65e934c8e549
Revises: 99784a953617
Create Date: 2026-09-21 03:48:50.841179

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '65e934c8e549'
down_revision: Union[str, Sequence[str], None] = '99784a953617'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default added by hand -- autogenerate doesn't propose one,
    # but the column is NOT NULL and existing rows need something (same
    # pattern as boss_kill_counts itself, migration f09e733c7c88).
    #
    # Autogenerate also proposed dropping 'ix_game_accounts_account_id'
    # here -- pre-existing drift between the live DB and the model (that
    # index exists in the DB but was never declared on the model),
    # unrelated to this change. Left alone on purpose, same as the last
    # migration that hit this (99784a953617) -- not touching a
    # production index as a side effect of an unrelated column add.
    op.add_column(
        'game_accounts',
        sa.Column(
            'boss_kill_counts_updated_at',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('game_accounts', 'boss_kill_counts_updated_at')
