"""add gear setup sort order

Revision ID: ac7e92357d68
Revises: ba756625a4e0
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ac7e92357d68'
down_revision: Union[str, Sequence[str], None] = 'ba756625a4e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the column backing a player's own drag-and-drop order for
    their list of gear setups (see GearSetup's docstring in
    app/models.py) -- nullable, and left NULL for every existing row on
    purpose. build_gear_setups in app/purchase_goals.py orders by this
    column first and created_at second, so as long as it's NULL
    (nothing dragged yet) the created_at tiebreaker alone decides the
    order -- oldest first, newest last, the new default -- and only
    once a player actually reorders their setups does this column get
    populated at all."""
    op.add_column(
        "gear_setups",
        sa.Column("sort_order", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gear_setups", "sort_order")
