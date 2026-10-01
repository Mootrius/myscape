"""add game account public code regenerated at

Revision ID: d1ef05233e91
Revises: 7f35b8214655
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1ef05233e91'
down_revision: Union[str, Sequence[str], None] = '7f35b8214655'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds GameAccount.public_code_regenerated_at -- the once-per-day
    throttle on POST /api/players/me/public-profile/regenerate-code
    (see that column's own comment in app/models.py). Null for every
    existing row, including any that already have a public_code from
    before this column existed -- their next regenerate is simply
    unthrottled the first time, same as a brand new code's first
    assignment always is."""
    op.add_column(
        "game_accounts",
        sa.Column("public_code_regenerated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("game_accounts", "public_code_regenerated_at")
