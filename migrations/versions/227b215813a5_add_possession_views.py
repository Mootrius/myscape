"""add possession views

Revision ID: 227b215813a5
Revises: e2a67f0c9d3b
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '227b215813a5'
down_revision: Union[str, Sequence[str], None] = 'e2a67f0c9d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """possession_views -- Storages Viewer's saved, named filter/sort
    configurations (see PossessionView's own docstring in
    app/models.py). config is one opaque JSON blob; sort_order is
    nullable and rewritten to plain integer positions on every
    drag-and-drop reorder, same shape as gear_setups.sort_order."""
    op.create_table(
        "possession_views",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_possession_views_player_id", "possession_views", ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_possession_views_player_id", table_name="possession_views")
    op.drop_table("possession_views")
