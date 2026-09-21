"""add item_id to goals

Revision ID: 271e77f0e2d4
Revises: 10baf11afbda
Create Date: 2026-09-21 17:41:31.375070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '271e77f0e2d4'
down_revision: Union[str, Sequence[str], None] = '10baf11afbda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds goals.item_id -- an item goal's real numeric OSRS item id
    (app.item_ids.find_item_ids' own id space), captured from whichever
    search suggestion the player actually picked in the redesigned
    add-goal wizard, purely so the goal list can show that item's real
    icon (item_icon_url in app/purchase_goals.py) instead of the
    generic item-goal badge. Nullable and purely a display hint -- an
    item goal's progress still resolves entirely from target_name (see
    app.goals.current_value), never from this column, so a goal
    created before this column existed, or one whose free-text name
    never matched a search result, just shows the generic badge
    instead of a broken/missing icon."""
    op.add_column("goals", sa.Column("item_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("goals", "item_id")
