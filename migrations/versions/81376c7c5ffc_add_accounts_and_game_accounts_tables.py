"""add accounts and game accounts tables

Revision ID: 81376c7c5ffc
Revises: 227b215813a5
Create Date: 2026-09-20 06:23:46.997549

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '81376c7c5ffc'
down_revision: Union[str, Sequence[str], None] = '227b215813a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Step one of the multi-account split (see
    docs/multi-account-scoping.md for the full plan) -- splits the
    login identity (email/password_hash/token_version/
    email_verified_at) out of Player into its own `accounts` table,
    and gives every existing player a matching `game_accounts` row
    that will take over as the FK target for a player's actual game
    data (bank items, skills, mindmaps, ...) in a later migration.

    Deliberately schema-only-plus-backfill: nothing reads from these
    two tables yet, no existing table's FK is repointed here, and
    `players` isn't touched beyond being read from. That keeps this
    safe to run and verify well ahead of the cutover migration that
    actually repoints everything and starts using accounts/
    game_accounts for real.

    game_accounts.id is deliberately set equal to the *existing*
    players.id it was backfilled from, not a freshly generated UUID.
    Every one of the ~24 tables that currently FKs to players.id
    (bank_items, gear_setups, mindmaps, loot_events, ...) already
    stores that exact UUID in every row it has. Keeping
    game_accounts.id identical means the later cutover migration can
    repoint those tables' FKs with a pure schema change -- rename the
    column, swap the constraint -- and never has to rewrite a single
    row of data across what could be a lot of item rows.
    accounts.id is a fresh UUID: nothing points at it yet, so there's
    no matching reason to preserve any existing value there.

    The backfill runs row-by-row in Python (generating each new
    account_id itself and reusing it for that one player's
    game_account.account_id) rather than as a SQL join, specifically
    to sidestep players.email being nullable (see Player.email's own
    docstring) -- joining accounts back to players by email would
    silently cross-multiply every admin-created, no-email row against
    every other one.
    """
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "game_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("runescape_name", sa.String(), nullable=True),
        sa.Column("account_hash", sa.String(), nullable=True, unique=True),
        sa.Column("skills", JSONB(), nullable=False, server_default="{}"),
        sa.Column("completed_quests", JSONB(), nullable=False, server_default="[]"),
        sa.Column("diary_tiers", JSONB(), nullable=False, server_default="{}"),
        sa.Column("storage_synced_at", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_game_accounts_account_id", "game_accounts", ["account_id"])

    accounts_table = sa.table(
        "accounts",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("email", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("token_version", sa.Integer()),
        sa.column("email_verified_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    game_accounts_table = sa.table(
        "game_accounts",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("account_id", UUID(as_uuid=True)),
        sa.column("runescape_name", sa.String()),
        sa.column("account_hash", sa.String()),
        sa.column("skills", JSONB()),
        sa.column("completed_quests", JSONB()),
        sa.column("diary_tiers", JSONB()),
        sa.column("storage_synced_at", JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    players_table = sa.table(
        "players",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("email", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("token_version", sa.Integer()),
        sa.column("email_verified_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("runescape_name", sa.String()),
        sa.column("account_hash", sa.String()),
        sa.column("skills", JSONB()),
        sa.column("completed_quests", JSONB()),
        sa.column("diary_tiers", JSONB()),
        sa.column("storage_synced_at", JSONB()),
    )

    bind = op.get_bind()
    existing_players = bind.execute(sa.select(players_table)).fetchall()

    account_rows = []
    game_account_rows = []
    for player in existing_players:
        account_id = uuid.uuid4()
        account_rows.append(
            {
                "id": account_id,
                "email": player.email,
                "password_hash": player.password_hash,
                "token_version": player.token_version,
                "email_verified_at": player.email_verified_at,
                "created_at": player.created_at,
            }
        )
        game_account_rows.append(
            {
                "id": player.id,  # preserved -- see docstring above
                "account_id": account_id,
                "runescape_name": player.runescape_name,
                "account_hash": player.account_hash,
                "skills": player.skills,
                "completed_quests": player.completed_quests,
                "diary_tiers": player.diary_tiers,
                "storage_synced_at": player.storage_synced_at,
                "created_at": player.created_at,
            }
        )

    if account_rows:
        bind.execute(accounts_table.insert(), account_rows)
    if game_account_rows:
        bind.execute(game_accounts_table.insert(), game_account_rows)


def downgrade() -> None:
    op.drop_index("ix_game_accounts_account_id", table_name="game_accounts")
    op.drop_table("game_accounts")
    op.drop_table("accounts")
