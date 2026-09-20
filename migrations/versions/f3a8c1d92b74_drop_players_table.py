"""drop the old players table

Revision ID: f3a8c1d92b74
Revises: 376936c4bb59
Create Date: 2026-09-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d92b74'
down_revision: Union[str, Sequence[str], None] = '376936c4bb59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Step 6 of the multi-account split (see
    docs/multi-account-scoping.md) -- the cleanup step, now that steps
    1/2 (81376c7c5ffc, 376936c4bb59) backfilled accounts/game_accounts
    from it and repointed every dependent table away from it, and
    steps 4/5/7 (app code) have been live in production long enough
    to prove out. `players` has had zero foreign-key dependents, in
    either direction, since 376936c4bb59 landed -- confirmed again
    directly against the schema right before writing this migration,
    not just inferred from reading that one's own docstring. Nothing
    in app/ has referenced the table or an ORM model backed by it
    since the step 4/5 rewrite.

    This is the one genuinely irreversible step in the whole plan --
    every prior migration only moved or duplicated data, this deletes
    a table outright. downgrade() below recreates the table's exact
    final shape (schema only) for completeness, but cannot bring back
    the rows: BACK UP THE DATABASE before running this against
    production, the same way you would before any DROP TABLE.
    """
    op.drop_table("players")


def downgrade() -> None:
    """Recreates `players` with the exact column set it had right
    before the drop (confirmed against the live schema, not just the
    original create_table -- skills/completed_quests/diary_tiers/
    storage_synced_at/token_version/email_verified_at were all added
    by later migrations after the table was first created). Schema
    only -- this cannot restore the rows that upgrade() deleted."""
    op.create_table(
        "players",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("runescape_name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("account_hash", sa.String(), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skills", JSONB(), nullable=False, server_default="{}"),
        sa.Column("completed_quests", JSONB(), nullable=False, server_default="[]"),
        sa.Column("diary_tiers", JSONB(), nullable=False, server_default="{}"),
        sa.Column("storage_synced_at", JSONB(), nullable=False, server_default="{}"),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
