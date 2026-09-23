"""add dashboard card order

Revision ID: c3f7a2e04d9b
Revises: e5fcc1ed7029
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'c3f7a2e04d9b'
down_revision: Union[str, Sequence[str], None] = 'e5fcc1ed7029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the column behind dashboard-card drag-and-drop reordering
    (see Account.dashboard_card_order and
    DASHBOARD_CARD_KEYS/resolve_dashboard_card_order's own docstrings in
    app/models.py and app/pages.py). Stays NULL for every existing
    account -- nobody's dashboard silently reorders itself the moment
    this ships; render_dashboard already treats NULL the same as "never
    dragged anything," same today's-hardcoded-order fallback as before
    this column existed."""
    op.add_column(
        "accounts",
        sa.Column("dashboard_card_order", JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("accounts", "dashboard_card_order")
