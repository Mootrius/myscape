"""add password reset tokens

Revision ID: 657a7ab7cea2
Revises: 5842ebde3965
Create Date: 2026-09-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '657a7ab7cea2'
down_revision: Union[str, Sequence[str], None] = '5842ebde3965'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds password_reset_tokens -- same shape as link_codes (see
    5cf359e6d5b1's own docstring for that one), just for the "forgot
    password" email flow instead of plugin linking (see
    PasswordResetToken's docstring in app/models.py)."""
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
