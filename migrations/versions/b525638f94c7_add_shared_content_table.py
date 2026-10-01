"""add shared content table

Revision ID: b525638f94c7
Revises: c5207ff090fd
Create Date: 2026-10-01 06:38:38.760947

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = 'b525638f94c7'
down_revision: Union[str, Sequence[str], None] = 'c5207ff090fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """shared_content -- the generic myscape.io/s/<code> share-link
    table (see SharedContent's own docstring in app/models.py). code
    gets its own unique index (not the primary key -- every lookup is
    by code, by a visitor who was handed a link, so this is the
    column that actually needs to be fast) alongside game_account_id's
    (every future "my shared links" listing will filter by owner)."""
    op.create_table(
        "shared_content",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("game_account_id", UUID(as_uuid=True), sa.ForeignKey("game_accounts.id"), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_shared_content_game_account_id", "shared_content", ["game_account_id"],
    )
    op.create_index(
        "ix_shared_content_code", "shared_content", ["code"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_shared_content_code", table_name="shared_content")
    op.drop_index("ix_shared_content_game_account_id", table_name="shared_content")
    op.drop_table("shared_content")
