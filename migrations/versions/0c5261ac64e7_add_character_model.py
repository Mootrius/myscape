"""add character model

Revision ID: 0c5261ac64e7
Revises: b7153da28d35
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c5261ac64e7'
down_revision: Union[str, Sequence[str], None] = 'b7153da28d35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('game_accounts', sa.Column('character_model_glb', sa.LargeBinary(), nullable=True))
    op.add_column('game_accounts', sa.Column('character_model_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('game_accounts', 'character_model_synced_at')
    op.drop_column('game_accounts', 'character_model_glb')
