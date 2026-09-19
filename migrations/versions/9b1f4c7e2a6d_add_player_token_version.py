"""add player token version

Revision ID: 9b1f4c7e2a6d
Revises: 657a7ab7cea2
Create Date: 2026-09-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9b1f4c7e2a6d'
down_revision: Union[str, Sequence[str], None] = '657a7ab7cea2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the counter backing "resetting a password invalidates every
    other already-logged-in session" (see Player.token_version's own
    docstring in app/models.py). Defaults to 0 for every existing row,
    matching what a freshly created player also gets -- there's nothing
    to invalidate yet for either."""
    op.add_column(
        "players",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("players", "token_version")
