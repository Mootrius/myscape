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
- [x] **Step 3 (`app/models.py`):** splits `Player` into `Account`
  (email, password_hash, token_version, email_verified_at,
  created_at) and `GameAccount` (account_hash, runescape_name,
  skills, completed_quests, diary_tiers, storage_synced_at, plus the
  24 character-scoped relationships), matching the schema the last
  two migrations already created. The 24 character-scoped child
  classes now FK to `game_accounts.id` via a `game_account_id`
  column and a `game_account` relationship; the 2 identity-scoped
  token classes now FK to `accounts.id` via `account_id`/`account`.
  Verified three ways: `sqlalchemy.orm.configure_mappers()` against
  the bare module (catches any back_populates mismatch immediately),
  then a real end-to-end run against a freshly migrated Postgres --
  created an `Account` with two linked `GameAccount`s (a main and an
  alt, the actual multi-account shape this whole project is for),
  added a `BankItem`/`GearSetup`/`PasswordResetToken` through the ORM
  relationships, re-fetched everything from scratch by querying (not
  reusing the same Python objects) to prove it round-trips through
  the real committed schema, and confirmed the account-hard-delete
  decision cascades correctly (deleting the `Account` removed both
  `GameAccount`s and every one of their item rows).

  Still not deployable on its own: every route in `app/main.py` and
  the other application modules (`app/auth.py`, `app/possessions.py`,
  `app/purchase_goals.py`, `app/loot.py`, `app/mindmaps.py`) still say
  `Player`/`player_id` and haven't been updated to `GameAccount`/
  `Account` yet -- that's steps 4 and 5.

## Scope correction after starting step 4

The original code-surface count (~120 touchpoints, `app/main.py` +
four business-logic modules) undercounted -- it missed
`app/routers/auth.py` (signup/login/logout/forgot-password/
reset-password/change-email/change-password/delete-account/
verify-email, 52 references), `app/routers/linking.py` (the
LinkCode/PlayerApiKey exchange itself, 15 references), and
`app/pages.py` (HTML rendering for every one of those pages plus the
dashboard, 23 references) entirely, and undercounted `app/main.py`
itself (189, not 78 -- the original grep pattern missed type
annotations and the `get_current_player_from_session`-family
dependency names). Real total across all 10 files: ~374.

This matters because the two biggest of those missed files are the
signup/login/password-reset/email-verification flow itself --
getting this wrong risks locking real users out, not just a broken
feature page.

### A real design wrinkle found while starting app/auth.py

Today, a brand new signup creates one `Player` row immediately, with
`account_hash = NULL` until the RuneLite link flow fills it in --
"signed up but not yet linked" is just a `Player` row with empty/null
game fields, not a missing row. After the split, that state has
nothing to attach to: a fresh `Account` has *zero* `GameAccount` rows
until linking creates one, so any session dependency that resolves
"the active GameAccount" has a real gap for that (common, expected)
state that didn't exist before.

The fix: signup creates an empty, unlinked `GameAccount` alongside
the new `Account`, exactly mirroring today's `account_hash = NULL`
initial state -- the first link-code exchange fills in that same row
(as it always has), and only a second linked account (the actual
multi-account feature, step 7) creates a *new* `GameAccount` row.
This preserves every existing signup/dashboard/link-flow behavior
with no new error states, and is the natural substrate multi-account
needs later anyway.

## Steps 4 and 5: the code layer, done in one pass

- [x] `app/auth.py`, `app/routers/auth.py`, `app/routers/linking.py`,
  `app/main.py`, `app/possessions.py`, `app/purchase_goals.py`,
  `app/loot.py`, `app/mindmaps.py`, `app/pages.py`, `app/schemas.py`
  (doc-only) -- every remaining `Player`/`player_id` reference across
  the app now says `Account`/`GameAccount`/`game_account_id`, and the
  whole app imports and runs again.

**This was found mid-refactor, not planned upfront**: after step 3
was committed and pushed, `app/main.py` (what Render actually boots
via `uvicorn app.main:app`) still imported the now-deleted `Player`
name at module load time, and `render.yaml` has no `autoDeploy:
false` -- so that push almost certainly took production down.
Confirmed by reproducing the exact `ImportError` locally against the
pushed commit. That turned steps 4/5 from "the next batch, in careful
order" into "get `app.main` importing again, now" -- the two ended up
being the same work, just done under time pressure instead of at a
leisurely pace. The lesson for next time: step 3 (the model split)
and step 4/5 (updating every consumer) probably shouldn't have been
separate commits/pushes in the first place, since nothing in between
them was ever actually deployable.

**The `Player`/`GameAccount` split wasn't 1:1 everywhere.** Most of
`app/main.py` and the four business-logic modules only ever needed
`GameAccount` (game data has no identity concept) -- a mechanical,
tokenize-based rename (Python's `tokenize` module, not plain regex,
so only real code identifiers were touched and prose/comments talking
about "the player" as a person were left alone) handled those safely
across hundreds of references. But the website's own server-rendered
pages (`app/pages.py`'s `render_dashboard`, `_footer`'s "Linked to
X" note, `_link_banner`'s verified-email gate, etc.) need *both*
identity fields (`email`, `email_verified_at`, from `Account`) and
game-data fields (`runescape_name`, `account_hash`, from the active
`GameAccount`) at once -- the exact same conflation `PlayerOut` (the
API response schema) already had, just on the HTML side. Fixed the
same way in both places: a small combined view built fresh per
request (`PlayerView` + `build_player_view` in `app/pages.py`, used
by a new `get_optional_current_player_view_from_session` dependency
in `app/auth.py`) rather than trying to make `GameAccount` or
`Account` alone carry fields that don't belong to it. `PlayerOut`
itself (the plugin/API-facing schema) is now built by hand at each of
the ~9 call sites from `account`/`game_account.account`, instead of
just returning the ORM row directly.

**Verified end-to-end against a real, freshly-migrated Postgres 16
database** (not just import/compile-clean): replayed all 26
migrations from scratch, then ran the *actual* FastAPI app (via
`TestClient`, no mocking) through signup (confirms it creates one
`Account` + one empty `GameAccount`) -> dashboard's unverified-redirect
-> email verification -> `/api/link/start` -> `/api/link/exchange`
(simulating the RuneLite plugin) -> `/api/players/me` (confirms the
combined identity+game-data response) -> a real bank sync via the
issued API key -> the website reading that bank data back over its
own session -> the dashboard footer actually showing "Linked to
<name>" -> unlink -> confirming the revoked API key now 401s -> a
second, independent signup. Then a second pass exercised the Mindmaps,
Loot Tracker, Storages Viewer, and Purchase Goals pages and their data
endpoints (create/list a mindmap, hide a loot NPC, read possession
trackers/summary, create a gear setup, read skills/quests/diaries) the
same way. `configure_mappers()` still passes. Still not run against
production -- only the throwaway local database.

**Still true and unchanged from before**: do not run `alembic upgrade
head` against production until this code is deployed. That boundary
was never actually at risk here -- the outage above was an import
error in already-deployed application code, unrelated to whether any
migration had been applied -- but it's worth restating since this was
the closest this project has come to a real incident.

**What's left**: steps 6 (drop the old `players` table, once this is
verified live in production) and 7 (the "link another account"
endpoint + account-switcher UI -- the backend substrate for it,
`GameAccount`/`_resolve_active_game_account`, already exists; nothing
in the UI calls it yet).

## Step 7: the account switcher

- [x] Four new endpoints in `app/routers/linking.py`: `GET
  /api/link/game-accounts` (list every `GameAccount` under the
  session's `Account`, each with `linked`/`active` flags), `POST
  /api/link/game-accounts` (create a new, empty, unlinked
  `GameAccount` and immediately make it the session's active one --
  the "+ ADD ANOTHER ACCOUNT" button), `POST
  /api/link/game-accounts/{id}/activate` (switch which one is active
  for this session, 404 if it doesn't belong to the calling
  `Account`), `DELETE /api/link/game-accounts/{id}` (hard-delete,
  cascades to every row that `GameAccount` owns via the existing
  SQLAlchemy `cascade="all, delete-orphan"` relationships -- no
  extra cleanup code needed; allowed all the way down to zero, per
  the "unlimited accounts, no minimum" decision above).
- [x] Account page UI (`app/pages.py`'s `render_account`): a new
  "LINKED ACCOUNTS" section listing every `GameAccount` with a
  Switch button (hidden on whichever is already active) and a
  two-step "ARE YOU SURE?" Remove button, plus the add button.
  Adding a slot does a full page reload so the existing `_link_banner`
  UI picks up the newly-active-but-unlinked `GameAccount` and shows
  its GENERATE CODE flow -- deliberately reusing that flow rather
  than building a second one.
- [x] `GameAccountSummary` schema added to `app/schemas.py` for the
  list endpoint's response shape.

**Bug caught by end-to-end testing, fixed before this was committed**:
`_player_out_for()` in `app/routers/auth.py` (written during steps
4/5, see above) built its `PlayerOut` from `account.game_accounts[0]`
-- always the *first* `GameAccount` ever linked, never the session's
actual active one. Harmless at the time (every `Account` had at most
one `GameAccount` until this step's own "add another account"
endpoint existed), and the function's own docstring already flagged
it as deferred to this step. Once a second `GameAccount` existed,
switching to it left `/api/auth/me` (and by extension every route
that calls `_player_out_for` -- `signup`, `login`, `reset_password`,
`verify_email`, `change_password`, `change_email`) silently showing
the wrong character's data. Fixed by having `_player_out_for` take
`request`/`db` and resolve the real active `GameAccount` via the
same `get_optional_current_game_account_from_session` dependency the
rest of the app already uses, instead of indexing into the list.
Caught by `smoke_test3.py`'s own assertion that `/api/auth/me`
reflects a freshly-activated second account -- it failed on the
first run, passed after this fix.

**Verified end-to-end** against a freshly-migrated throwaway
Postgres 16 database (all 26 migrations replayed from scratch): the
full switcher lifecycle (list -> add second, unlinked, active -> `me`
reflects it -> link it under a second `account_hash` -> switch back
to the first -> `me` reflects that -> cross-account activate attempt
404s -> delete the second, confirmed gone from the DB, not just
unlinked -> account page still renders -> delete the *last* remaining
one too, confirmed allowed, dashboard/account pages still render with
zero linked characters). Then a separate broader regression pass
against the same database: signup, email verification, login,
`/api/link/start`+`/api/link/exchange` (the RuneLite plugin's actual
flow), the issued API key against `/api/players/me` and a real bank
sync, and the dashboard/loot/possessions pages and
`/api/possessions/summary` all still 200. `configure_mappers()` and
route registration (120 routes, up from 116 before this step's 4
additions) both still clean. Not run against production -- only the
throwaway local database, same as steps 4/5.

**What's left**: step 6 only (drop the old `players` table, once this
step has had time to prove stable in production). Step 7 itself is
now complete.
