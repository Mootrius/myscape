# Multi-account support — scoping (Account/GameAccount split)

Scoping pass for letting one website login track more than one OSRS
character, done via the "textbook" fix: splitting the login identity
from the game character at the schema level, rather than a lighter
patch on top of the current `Player` model. Not yet implemented —
this is the plan to review before any code changes.

## Baseline: what `Player` is doing today

`Player` currently does two jobs in one row: it's the **login**
(`email`, `password_hash`, `token_version`, `email_verified_at`) and
it's the **character** (`account_hash`, `runescape_name`, `skills`,
`completed_quests`, `diary_tiers`, `storage_synced_at`, and the FK
target for every piece of game data).

26 tables FK directly to `players.id`:

- **Identity-scoped (stays with the login going forward):**
  `PasswordResetToken`, `EmailVerificationToken`
- **Character-scoped (moves to the new game-account table):**
  `LinkCode`, `PlayerApiKey`, `BankItem`, `InventoryItem`,
  `EquipmentItem`, `PotionStorageItem`, `RunePouchItem`,
  `SeedVaultItem`, `LootingBagItem`, `TackleBoxItem`, `PohItem`,
  `ForestryKitItem`, `MasterScrollBookItem`, `SeedBoxItem`,
  `HuntsmansKitItem`, `BoatCargoItem`, `GearSetup`, `MindMap`,
  `LootEvent`, `PossessionTracker`, `PinnedPossessionItem`,
  `HiddenLootEntry`, `HiddenPossessionStorage`, `PossessionView`
  (24 tables)

Plus six fields currently living directly on `Player` that are
character data, not identity data, and need to move with the rest:
`account_hash`, `runescape_name`, `skills`, `completed_quests`,
`diary_tiers`, `storage_synced_at`.

## New shape

- **`Account`** (the login): `id`, `email`, `password_hash`,
  `token_version`, `email_verified_at`, `created_at`. Owns
  `PasswordResetToken` / `EmailVerificationToken`, and one-to-many
  `GameAccount`.
- **`GameAccount`** (the character): `id`, `account_id` (FK to
  `Account`), `account_hash`, `runescape_name`, `skills`,
  `completed_quests`, `diary_tiers`, `storage_synced_at`,
  `created_at`. Owns `PlayerApiKey`, `LinkCode`, and all 24
  character-scoped game-data tables (FK column renamed
  `player_id` -> `game_account_id`).

## Code surface (measured, not estimated)

Grepped the actual codebase for `player_id` / `player.<attr>`
touchpoints:

| File | References | Notes |
|---|---|---|
| `app/main.py` | 78 | Every route lives here — the largest chunk of mechanical rewrite work. |
| `app/auth.py` (150 lines total) | 9 | The entire session/cookie/token-version/API-key layer, in 4 dependency functions: `get_current_player_from_api_key`, `get_current_player_from_session`, `get_optional_current_player_from_session`, `get_current_verified_player_from_session`. This is the file that grows an "active GameAccount" concept alongside "authenticated Account." |
| `app/purchase_goals.py` (1151 lines) | 13 | |
| `app/possessions.py` (599 lines) | 10 | |
| `app/loot.py` (684 lines) | 10 | |
| `app/mindmaps.py` (1027 lines) | 1 | |
| `app/schemas.py` (1524 lines) | 1 | |

Plus 26 FK columns and ~52 `relationship()`/`back_populates`
declarations in `app/models.py` itself.

**Total: ~120 direct touchpoints**, concentrated almost entirely in
`main.py` + `auth.py`. The four business-logic modules mostly take an
already-resolved row as a parameter rather than re-deriving "the
player" themselves, so most of their internals won't need real logic
changes — just what type of row flows through them (swap `player_id`
for `game_account_id`, rename a variable).

## RuneLite plugin side — no changes needed

Checked `myscape-plugin` directly (`MyscapeClient.java`,
`MyscapeConfig.java`): the plugin stores its API key via RuneLite's
own `ConfigManager` (`configManager.setConfiguration(...)`), which is
scoped per RuneLite **profile** — and RuneLite already supports one
profile per game account natively (this is exactly how existing OSRS
multi-accounters already run RuneLite). Every link-code exchange
already produces and stores its own independent API key, per profile,
with zero cross-talk between accounts.

**The plugin needs zero code changes for this feature.** The only
thing that changes is server-side: whether a second successful
link-code exchange, from a second RuneLite profile, is allowed to
attach a new `GameAccount` to an `Account` that already has one, and
which row its `PlayerApiKey` ends up pointing at.

## Data migration plan (the risky part)

Alembic-managed (24 existing migrations in `migrations/versions/`),
so this fits the existing tooling.

For every existing `Player` row, this is a clean **1:1 remap**, not a
fuzzy merge — every old row becomes exactly one `Account` + one
`GameAccount`:

1. Create an `Account` row carrying its
   `email`/`password_hash`/`token_version`/`email_verified_at`/`created_at`.
2. Create a `GameAccount` row carrying its
   `account_hash`/`runescape_name`/`skills`/`completed_quests`/`diary_tiers`/`storage_synced_at`/`created_at`,
   with `account_id` pointing at the new `Account` row.
3. Rewrite the FK column on all 24 character-scoped tables from
   `player_id` to the new `GameAccount`'s id.
4. Rewrite `PasswordResetToken`/`EmailVerificationToken`'s
   `player_id` to point at the new `Account`'s id instead.

Because it's a 1:1 remap at migration time, the actual SQL is
mechanical rather than ambiguous — that de-risks it somewhat versus a
migration that has to decide how to merge multiple old rows into one
new one. Still needs:

- To run inside a single transaction.
- A full dry run against a copy of production data, not just a dev
  DB with a handful of rows.
- A plan for sessions signed *before* the migration, which reference
  the old `Player.id`/`token_version` shape — either force everyone
  to log in again once at cutover, or build a compatibility shim.

## New work once the split exists

- `app/auth.py`: session carries both "which `Account` is
  authenticated" and "which `GameAccount` is currently active," plus
  a switch endpoint that validates the target `GameAccount.account_id`
  matches the authenticated `Account` before trusting a switch.
- A "link another account" endpoint: while authenticated, create a
  new `GameAccount` row under the same `Account`, generate a
  `LinkCode` for it exactly like signup does today, and hand it to
  the existing (unmodified) plugin linking flow.
- UI: an account switcher (dropdown of linked characters + "add
  another"), reusing the existing linking screen for account #2+.

## Suggested sequencing

1. Alembic migration: create `accounts` + `game_accounts` tables,
   backfill from `players` (script only — nothing cut over yet).
2. Second migration: repoint the 24 character-scoped tables' FKs +
   the 2 identity tables' FKs, once the backfill is verified against
   a full copy of prod data.
3. `app/models.py`: `Account`/`GameAccount` classes, relationship
   renames.
4. `app/auth.py`: `Account`-based auth + active-`GameAccount`
   resolution + switch endpoint.
5. `app/main.py` + the four business-logic modules: swap `player` for
   "active game account" at each of the ~120 touchpoints — mechanical,
   verifiable file by file.
6. Drop the old `players` table once verified in production.
7. Build "link another account" + switcher UI on top.

## Decisions

- No cap on accounts per login -- unlimited.
- Removing a linked account hard-deletes it (cascades its ~24 tables
  of data), no detach-and-orphan option.
- Existing sessions get force-logged-out once at cutover, rather than
  building a compatibility shim for old-shaped cookies -- this only
  affects the website's own login cookie, never the RuneLite plugin's
  API key (which isn't a cookie at all, see the plugin section above).

## Progress

- [x] **Step 1 (migration `81376c7c5ffc`):** creates `accounts` and
  `game_accounts`, backfills both from every existing `players` row.
  `game_accounts.id` is deliberately kept identical to the `players.id`
  it came from (see the migration's own docstring for why), so the
  later FK-repoint migration never has to rewrite a row of item data.
  Verified end-to-end against a real throwaway Postgres 16 instance:
  replayed all 24 prior migrations, seeded rows including two
  different NULL-email players (the exact case that would break a
  join-based backfill), ran upgrade, confirmed id-preservation and
  correct account<->game_account pairing with no cross-contamination,
  then downgrade, then upgrade again -- clean round trip. Nothing
  reads from these two tables yet; `players` and every existing route
  are untouched so far.
- [x] **Step 2 (migration `376936c4bb59`):** the actual cutover.
  Repoints all 24 character-scoped tables' `player_id` at
  `game_accounts` (pure schema change -- drop constraint, rename
  column, add constraint, rename the unique constraints/indexes that
  reference it -- no row data rewritten, since `game_accounts.id`
  already equals the old `player_id` values), and repoints the 2
  identity-scoped token tables' `player_id` at `accounts` as
  `account_id` (a real value rewrite this time, via a join through
  `game_accounts` as the bridge). Caught and handled `poh_items`'
  irregular FK constraint name (`costume_room_items_player_id_fkey`,
  a leftover from before that table was renamed) by introspecting the
  real replayed schema rather than assuming a name. Verified the same
  way as step 1 -- seeded real rows in `bank_items`, `gear_setups`,
  `poh_items`, `possession_trackers`, and both token tables against a
  live player, ran upgrade, confirmed every FK/constraint/index landed
  correctly and every token pointed at the *right* account, then
  downgrade and diffed the schema back to byte-for-byte identical
  (including `poh_items`' irregular name), then upgrade again. Still
  doesn't touch `players` itself, and no application code
  (`app/main.py`, `app/auth.py`, `app/models.py`, ...) has been
  updated yet -- the ORM models and every route still read/write the
  old `player_id` columns, so right now the live schema and the ORM's
  idea of the schema have diverged. That gets fixed in step 3.
