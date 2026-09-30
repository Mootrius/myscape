"""drop dashboard card order

Revision ID: 6be2c31cceaa
Revises: b3571fb3eb33
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '6be2c31cceaa'
down_revision: Union[str, Sequence[str], None] = 'b3571fb3eb33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drops the column behind the dashboard's own per-player drag-and-
    drop card reorder (see c3f7a2e04d9b_add_dashboard_card_order, and
    DASHBOARD_CARD_KEYS' own comment in app/pages.py) -- removed per
    explicit instruction in favor of one fixed card order for every
    player, with nothing left anywhere in the app that still reads or
    writes this column."""
    op.drop_column("accounts", "dashboard_card_order")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "accounts",
        sa.Column("dashboard_card_order", JSONB(), nullable=True),
    )
