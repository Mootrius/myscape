"""add game account model viewer background index

Revision ID: c5207ff090fd
Revises: 9b1c6e3a4d7f
Create Date: 2026-10-01 05:09:41.966337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5207ff090fd'
down_revision: Union[str, Sequence[str], None] = '9b1c6e3a4d7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds GameAccount.model_viewer_background_index -- an index into
    _MODEL_VIEWER_BACKGROUNDS (app/pages.py), set by POST /api/players/
    me/model-viewer-background whenever a player shuffles their
    Character Overview model-viewer background (see that column's own
    comment in app/models.py). Null for every existing row until their
    next shuffle -- treated the same as every never-synced value
    elsewhere on this page, falling back to index 0, the same default
    every Character Overview already opens on pre-shuffle anyway."""
    op.add_column(
        "game_accounts",
        sa.Column("model_viewer_background_index", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("game_accounts", "model_viewer_background_index")
