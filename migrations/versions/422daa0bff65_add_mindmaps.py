"""add mindmaps

Revision ID: 422daa0bff65
Revises: b84c0fc0163c
Create Date: 2026-09-15 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '422daa0bff65'
down_revision: Union[str, Sequence[str], None] = 'b84c0fc0163c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds mindmaps -- a player's named goal/idea trees (the Mindmaps
    feature). Same shape as gear_setups: `nodes` is one JSONB blob
    (a flat list of {id, parentId, text, color, order} dicts) rather
    than a normalized child table, since a mindmap is always read and
    written as a whole -- see MindMap's docstring in app/models.py."""
    op.create_table(
        "mindmaps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nodes", JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mindmaps")
