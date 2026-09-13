"""initial schema

Revision ID: 5cf359e6d5b1
Revises:
Create Date: 2026-09-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '5cf359e6d5b1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create players/link_codes/player_api_keys -- but only whichever
    of them don't already exist.

    This migration is retrofitted onto a database that, in production,
    was never created by Alembic in the first place: it was built up
    over time by Base.metadata.create_all() (which only ever adds
    brand-new tables) plus schema_sync.sync_missing_columns() (which
    patched columns onto tables that already existed), both now
    removed in favor of Alembic (see app/main.py and README.md's
    "Database schema changes"). Running this migration against that
    already-populated database has to be a no-op on the tables
    themselves -- the has_table() checks below are what make that
    true, so there's no separate manual "tell Alembic this database is
    already at the initial migration" step to remember to run against
    production. Running it against a genuinely empty database (local
    dev, a fresh environment) creates everything from scratch, exactly
    like create_all() used to.

    The column/constraint shapes below match what create_all() +
    sync_missing_columns() actually produced in production as of this
    migration (verified against a throwaway database built the old
    way -- see the commit message), not just what app/models.py says
    today -- those two happen to agree right now, but this file is a
    frozen historical record either way, the same as any other
    migration: future model changes get their own new migration, they
    never edit this one.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "players" not in existing_tables:
        op.create_table(
            "players",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("runescape_name", sa.String(), nullable=True),
            sa.Column("email", sa.String(), nullable=True, unique=True),
            sa.Column("password_hash", sa.String(), nullable=True),
            sa.Column("account_hash", sa.String(), nullable=True, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "link_codes" not in existing_tables:
        op.create_table(
            "link_codes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("code_hash", sa.String(), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "player_api_keys" not in existing_tables:
        op.create_table(
            "player_api_keys",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("key_hash", sa.String(), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Drops all three tables unconditionally -- if you're downgrading
    past this migration you want them gone regardless of whether this
    particular run was the one that created them."""
    op.drop_table("player_api_keys")
    op.drop_table("link_codes")
    op.drop_table("players")
