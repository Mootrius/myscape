"""add icon_cache_entries table

Revision ID: e1b6d3a94f27
Revises: c4e8a1b7d205
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1b6d3a94f27'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1b7d205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """icon_cache_entries -- see IconCacheEntry's docstring in app/models.py.
    Starts empty; app/icon_cache.py fills it from the wiki on demand."""
    op.create_table(
        "icon_cache_entries",
        sa.Column("filename", sa.String(), primary_key=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("icon_cache_entries")
