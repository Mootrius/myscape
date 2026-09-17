"""add hidden possession storages

Revision ID: ba756625a4e0
Revises: 3192ede99dfa
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'ba756625a4e0'
down_revision: Union[str, Sequence[str], None] = '3192ede99dfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """hidden_possession_storages -- Storages Viewer's per-storage
    on/off setting (see HiddenPossessionStorage's own docstring in
    app/models.py). One row per (player, storage_key) currently
    switched off; deleting the row switches it back on. No row for a
    player means every storage reads as on, so no backfill is needed
    for existing players."""
    op.create_table(
        "hidden_possession_storages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "storage_key", name="uq_hidden_possession_storages_player_key"),
    )
    op.create_index(
        "ix_hidden_possession_storages_player_id", "hidden_possession_storages", ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_hidden_possession_storages_player_id", table_name="hidden_possession_storages")
    op.drop_table("hidden_possession_storages")
