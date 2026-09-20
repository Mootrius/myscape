"""repoint character and identity tables at game accounts and accounts

Revision ID: 376936c4bb59
Revises: 81376c7c5ffc
Create Date: 2026-09-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '376936c4bb59'
down_revision: Union[str, Sequence[str], None] = '81376c7c5ffc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every table that currently FKs to players.id, split into the two
# groups from docs/multi-account-scoping.md. Each entry is:
#   (table_name, existing_fk_constraint_name, unique_suffix, unique_other_columns, has_plain_index)
# unique_suffix/unique_other_columns are None where that table has no
# extra uniqueness on player_id beyond the FK itself (link_codes,
# player_api_keys, gear_setups, mindmaps); has_plain_index is True for
# the tables whose model also declared player_id with index=True
# (loot_events, possession_trackers, pinned_possession_items,
# hidden_loot_entries, hidden_possession_storages, possession_views).
#
# poh_items is the one irregular case: its FK constraint is still
# named costume_room_items_player_id_fkey, a leftover from before that
# table was renamed (see PohItem's own docstring in app/models.py) --
# Postgres never renames a constraint just because the table it's on
# got renamed, so this migration has to know the real, current name
# rather than guessing "poh_items_player_id_fkey" (confirmed against
# a real replay of every prior migration, not assumed).
CHARACTER_SCOPED_TABLES = [
    ("link_codes", "link_codes_player_id_fkey", None, None, False),
    ("player_api_keys", "player_api_keys_player_id_fkey", None, None, False),
    ("bank_items", "bank_items_player_id_fkey", "item", ["item_id"], False),
    ("inventory_items", "inventory_items_player_id_fkey", "item", ["item_id"], False),
    ("equipment_items", "equipment_items_player_id_fkey", "slot", ["slot"], False),
    ("potion_storage_items", "potion_storage_items_player_id_fkey", "item", ["item_id"], False),
    ("rune_pouch_items", "rune_pouch_items_player_id_fkey", "item", ["item_id"], False),
    ("seed_vault_items", "seed_vault_items_player_id_fkey", "item", ["item_id"], False),
    ("looting_bag_items", "looting_bag_items_player_id_fkey", "item", ["item_id"], False),
    ("tackle_box_items", "tackle_box_items_player_id_fkey", "item", ["item_id"], False),
    ("poh_items", "costume_room_items_player_id_fkey", "item", ["item_id"], False),
    ("forestry_kit_items", "forestry_kit_items_player_id_fkey", "item", ["item_id"], False),
    ("master_scroll_book_items", "master_scroll_book_items_player_id_fkey", "item", ["item_id"], False),
    ("seed_box_items", "seed_box_items_player_id_fkey", "item", ["item_id"], False),
    ("huntsmans_kit_items", "huntsmans_kit_items_player_id_fkey", "item", ["item_id"], False),
    ("boat_cargo_items", "boat_cargo_items_player_id_fkey", "slot_item", ["slot", "item_id"], False),
    ("gear_setups", "gear_setups_player_id_fkey", None, None, False),
    ("mindmaps", "mindmaps_player_id_fkey", None, None, False),
    ("loot_events", "loot_events_player_id_fkey", "event", ["event_id"], True),
    ("possession_trackers", "possession_trackers_player_id_fkey", "kind_item", ["kind", "item_id"], True),
    ("pinned_possession_items", "pinned_possession_items_player_id_fkey", "item", ["item_id"], True),
    ("hidden_loot_entries", "hidden_loot_entries_player_id_fkey", "kind_key", ["kind", "key"], True),
    ("hidden_possession_storages", "hidden_possession_storages_player_id_fkey", "key", ["storage_key"], True),
    ("possession_views", "possession_views_player_id_fkey", None, None, True),
]

# The two token tables that stay identity-scoped (see
# docs/multi-account-scoping.md) -- unlike the tables above, these
# genuinely need their player_id *values* rewritten, since
# accounts.id is a fresh UUID rather than one preserved from players
# (compare game_accounts.id, which step one's migration deliberately
# kept identical to players.id for exactly this reason). The rewrite
# UPDATE below joins through game_accounts as the bridge -- game_accounts.id
# still equals the original players.id at this point, and
# game_accounts.account_id is already the right new accounts.id -- so
# it doesn't need players or any other lookup, and works whether or
# not the players table still exists by the time this ever gets
# copy-adapted for a similar future migration.
IDENTITY_SCOPED_TABLES = [
    ("password_reset_tokens", "password_reset_tokens_player_id_fkey"),
    ("email_verification_tokens", "email_verification_tokens_player_id_fkey"),
]


def upgrade() -> None:
    """Step two of the multi-account split (see
    docs/multi-account-scoping.md) -- the actual cutover. Repoints
    every character-scoped table's player_id at game_accounts instead
    of players (a pure schema change: drop constraint, rename column,
    add constraint -- no row data touched, since game_accounts.id was
    deliberately kept identical to players.id by the prior migration),
    and repoints the two identity-scoped token tables' player_id at
    accounts instead (a real value rewrite this time, via the
    game_accounts bridge -- see IDENTITY_SCOPED_TABLES above).

    Does NOT touch app/main.py, app/auth.py, or any other application
    code, and does NOT drop the players table -- those come in later
    steps once the ORM/routes have been updated to actually use the
    new column names. `players` is left fully intact and still has
    every column it had before; nothing in this migration reads from
    or writes to it at all.
    """
    for table, old_fk, unique_suffix, unique_cols, has_plain_index in CHARACTER_SCOPED_TABLES:
        op.drop_constraint(old_fk, table, type_="foreignkey")
        if unique_suffix:
            op.drop_constraint(f"uq_{table}_player_{unique_suffix}", table, type_="unique")
        if has_plain_index:
            op.drop_index(f"ix_{table}_player_id", table_name=table)

        op.alter_column(table, "player_id", new_column_name="game_account_id")

        op.create_foreign_key(
            f"{table}_game_account_id_fkey", table, "game_accounts", ["game_account_id"], ["id"]
        )
        if unique_suffix:
            op.create_unique_constraint(
                f"uq_{table}_game_account_{unique_suffix}", table, ["game_account_id"] + unique_cols
            )
        if has_plain_index:
            op.create_index(f"ix_{table}_game_account_id", table, ["game_account_id"])

    for table, old_fk in IDENTITY_SCOPED_TABLES:
        op.drop_constraint(old_fk, table, type_="foreignkey")
        op.execute(
            f"UPDATE {table} SET player_id = game_accounts.account_id "
            f"FROM game_accounts WHERE {table}.player_id = game_accounts.id"
        )
        op.alter_column(table, "player_id", new_column_name="account_id")
        op.create_foreign_key(f"{table}_account_id_fkey", table, "accounts", ["account_id"], ["id"])


def downgrade() -> None:
    """Reverses upgrade() exactly, table by table, restoring the
    original column/constraint/index names -- including poh_items'
    irregular costume_room_items_player_id_fkey name, so a downgrade
    leaves the schema byte-for-byte how the prior migration left it."""
    for table, old_fk in IDENTITY_SCOPED_TABLES:
        op.drop_constraint(f"{table}_account_id_fkey", table, type_="foreignkey")
        op.execute(
            f"UPDATE {table} SET account_id = game_accounts.id "
            f"FROM game_accounts WHERE {table}.account_id = game_accounts.account_id"
        )
        op.alter_column(table, "account_id", new_column_name="player_id")
        op.create_foreign_key(old_fk, table, "players", ["player_id"], ["id"])

    for table, old_fk, unique_suffix, unique_cols, has_plain_index in reversed(CHARACTER_SCOPED_TABLES):
        if has_plain_index:
            op.drop_index(f"ix_{table}_game_account_id", table_name=table)
        if unique_suffix:
            op.drop_constraint(f"uq_{table}_game_account_{unique_suffix}", table, type_="unique")
        op.drop_constraint(f"{table}_game_account_id_fkey", table, type_="foreignkey")

        op.alter_column(table, "game_account_id", new_column_name="player_id")

        op.create_foreign_key(old_fk, table, "players", ["player_id"], ["id"])
        if unique_suffix:
            op.create_unique_constraint(
                f"uq_{table}_player_{unique_suffix}", table, ["player_id"] + unique_cols
            )
        if has_plain_index:
            op.create_index(f"ix_{table}_player_id", table, ["player_id"])
