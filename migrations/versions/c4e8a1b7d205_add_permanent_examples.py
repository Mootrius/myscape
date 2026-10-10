"""add permanent_examples table

Revision ID: c4e8a1b7d205
Revises: a7d3f1c2e9b4
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = 'c4e8a1b7d205'
down_revision: Union[str, Sequence[str], None] = 'a7d3f1c2e9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """permanent_examples -- see PermanentExample's docstring in
    app/models.py. No foreign keys on purpose. The rows themselves are
    filled in by app/permanent_examples.py at startup, not here."""
    op.create_table(
        "permanent_examples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("owner_name", sa.String(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("model_glb", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code", name="uq_permanent_examples_code"),
    )


def downgrade() -> None:
    op.drop_table("permanent_examples")
