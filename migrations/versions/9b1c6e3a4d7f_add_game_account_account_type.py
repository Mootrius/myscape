"""add game account account type

Revision ID: 9b1c6e3a4d7f
Revises: d1ef05233e91
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1c6e3a4d7f'
down_revision: Union[str, Sequence[str], None] = 'd1ef05233e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds GameAccount.account_type -- one of "MAIN"/"IRONMAN"/"UIM"/
    "HCIM"/"GIM"/"HCGIM"/"UGIM" (see that column's own comment in
    app/models.py). Null for every existing row until their next
    character-summary sync, same "never synced" meaning every other
    character_summary_* field uses -- Character Overview's account-
    type tile (replacing the old geValue/"Net worth" tile) treats that
    the same way every other never-synced stat on this page already
    is, an em dash rather than a wrong/default account type."""
    op.add_column(
        "game_accounts",
        sa.Column("account_type", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("game_accounts", "account_type")
