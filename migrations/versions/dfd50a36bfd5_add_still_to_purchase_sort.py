"""add still to purchase sort

Revision ID: dfd50a36bfd5
Revises: 71ab8e8afc06
Create Date: 2026-09-14 05:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'dfd50a36bfd5'
down_revision: Union[str, Sequence[str], None] = '71ab8e8afc06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the two columns backing per-setup "Still to Purchase" list
    ordering (see GearSetup's docstring in app/models.py):
    still_to_purchase_sort_mode ("low_to_high" -- the pre-existing,
    only-ever behavior before this, now the explicit default --
    "high_to_low", or "custom") and still_to_purchase_custom_order (the
    player's own drag-and-drop ordering, only ever populated once they
    actually reorder something in "custom" mode)."""
    op.add_column(
        "gear_setups",
        sa.Column("still_to_purchase_sort_mode", sa.String(), nullable=False, server_default="low_to_high"),
    )
    op.add_column(
        "gear_setups",
        sa.Column("still_to_purchase_custom_order", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gear_setups", "still_to_purchase_custom_order")
    op.drop_column("gear_setups", "still_to_purchase_sort_mode")
