"""add game account public profile

Revision ID: 7f35b8214655
Revises: 6be2c31cceaa
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f35b8214655'
down_revision: Union[str, Sequence[str], None] = '6be2c31cceaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the public-profile pair behind myscape.io/c/<code> -- see
    GameAccount.is_public_profile/public_code's own comments in
    app/models.py. is_public_profile defaults false for every existing
    character, same as every other opt-in flag added here -- nothing
    becomes unexpectedly shareable on deploy. public_code stays NULL
    until a character's first opt-in (generate_public_code in
    app/public_profile.py assigns it then, not this migration), so no
    backfill is needed; its unique index still has to be created
    explicitly since op.add_column's own unique=True kwarg doesn't
    reliably emit one on every backend the way op.create_table's does."""
    op.add_column(
        "game_accounts",
        sa.Column("is_public_profile", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "game_accounts",
        sa.Column("public_code", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_game_accounts_public_code",
        "game_accounts",
        ["public_code"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_game_accounts_public_code", table_name="game_accounts")
    op.drop_column("game_accounts", "public_code")
    op.drop_column("game_accounts", "is_public_profile")
