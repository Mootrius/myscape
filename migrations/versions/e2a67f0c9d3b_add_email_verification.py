"""add email verification

Revision ID: e2a67f0c9d3b
Revises: 9b1f4c7e2a6d
Create Date: 2026-09-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'e2a67f0c9d3b'
down_revision: Union[str, Sequence[str], None] = '9b1f4c7e2a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds Player.email_verified_at and email_verification_tokens (see
    both of their own docstrings in app/models.py). Every row that
    already exists gets backfilled to "verified right now" -- these
    accounts were all created and used successfully long before this
    feature existed, so there's nothing to gain by suddenly locking
    every one of them out; only a signup from this point on starts out
    unverified and has to click a confirmation link."""
    op.add_column(
        "players",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE players SET email_verified_at = now() WHERE email_verified_at IS NULL")

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("email_verification_tokens")
    op.drop_column("players", "email_verified_at")
