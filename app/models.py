"""SQLAlchemy models.

Account linking is a two-phase handoff between the website and the
RuneLite plugin, deliberately stronger than the "one long-lived code
typed into a settings field" pattern used by sites like Wise Old Man:

  1. LINK CODE -- short-lived (10 minutes) and single-use. The website
     generates it for a signed-in player and shows it to them; they
     paste it into the plugin's settings once. We store only a SHA-256
     hash of it, never the raw value.
  2. API KEY -- the plugin immediately exchanges the link code (exactly
     once -- see PlayerApiKey.consumed_at... actually the code itself is
     what's single-use, see LinkCode.used_at) for a separate, long-lived
     API key. The plugin stores *that* in its local config and sends it
     with every future data-upload request. Only its hash is stored
     server-side too.

Splitting these matters: the short-lived code only needs to survive a
copy/paste, so if it leaks (shoulder-surfed, pasted into the wrong
place) the window of exposure is minutes and it can't be replayed. The
API key is the thing doing real, repeated work, so it's the one that's
revocable independent of the player ever re-linking.

The link is bound to RuneLite's stable per-account `account_hash`
(rather than the self-reported, mutable OSRS display name) so a name
change doesn't break tracking or let someone else's freshly-renamed
account inherit history that isn't theirs.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base

LINK_CODE_LIFETIME = timedelta(minutes=10)
# Longer than LINK_CODE_LIFETIME on purpose -- a link code is shown
# on-screen for an immediate copy/paste into the plugin, but a
# password reset token has to survive an email actually arriving and
# the player noticing it, so it needs real slack. An hour is generous
# enough for that without leaving a stale, unused reset link valid for
# days.
PASSWORD_RESET_TOKEN_LIFETIME = timedelta(hours=1)

# Deliberately longer than PASSWORD_RESET_TOKEN_LIFETIME above -- a
# password reset is meant to be acted on right away (it exists because
# someone's locked out *right now*), but confirming a freshly signed-up
# email is lower-stakes and easy to put off for a day, so this gives
# more slack before a player has to ask for a fresh link.
EMAIL_VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)


def _utcnow():
    return datetime.now(timezone.utc)


def _as_aware_utc(value):
    """SQLite (used for local/dev testing) doesn't preserve tzinfo on
    DateTime(timezone=True) columns the way Postgres does, so a value
    read back can come back naive. Treat a naive value as already UTC
    rather than letting the comparison below raise."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class Account(Base):
    """The website login -- email, password, and everything about
    verifying who's signing in. Split out from what used to be one
    combined Player row (see GameAccount just below, and
    docs/multi-account-scoping.md for the full multi-account plan) so
    that one login can own more than one linked OSRS character: an
    Account has many GameAccounts, not the other way around."""

    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=True, unique=True)
    # Nullable because it's meaningless for a row that only ever gets
    # created by admin tooling; every row created through the real
    # signup endpoint always has one.
    password_hash = Column(String, nullable=True)
    # Bumped whenever the password changes via /api/auth/reset-password
    # (see that endpoint in app/routers/auth.py). The session cookie
    # set at login carries a snapshot of this value (see log_in_player
    # in app/auth.py); a session whose snapshot no longer matches the
    # account's current value is treated as stale and logged out. That's
    # what actually invalidates every *other* already-logged-in session
    # the moment a password gets reset -- sessions are just signed
    # cookies here (no server-side session store to delete rows from),
    # so this counter is the only lever available for "log everyone
    # else out."
    token_version = Column(Integer, nullable=False, default=0)
    # NULL until the player clicks the link from their confirmation
    # email (see POST /api/auth/verify-email in app/routers/auth.py),
    # then set to when that happened. get_current_verified_player_from_session
    # in app/auth.py requires this to be set for most of the site --
    # see that function's own docstring for exactly what stays
    # reachable before verification. Every row that existed before this
    # column did gets backfilled to "verified" by its own migration
    # (9b1f4c7e2a6d's successor) rather than suddenly locking out every
    # existing account -- only accounts created from that point on
    # start out unverified.
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    game_accounts = relationship("GameAccount", back_populates="account", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="account", cascade="all, delete-orphan")
    email_verification_tokens = relationship("EmailVerificationToken", back_populates="account", cascade="all, delete-orphan")


class GameAccount(Base):
    """One linked OSRS character and everything the RuneLite plugin
    actually reports for it -- skills, quests, bank, gear, and every
    other item-source table below. This is what Player used to be
    before the multi-account split (see Account just above, and
    docs/multi-account-scoping.md) -- owned by exactly one Account, but
    an Account can own more than one GameAccount, since a person can
    link more than one OSRS character under a single myscape login."""

    __tablename__ = "game_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    # The player's OSRS display name, as reported by the RuneLite plugin
    # once it's linked. Mutable (players rename), so it's informational,
    # never the identity key -- that's account_hash below.
    runescape_name = Column(String, nullable=True)
    # RuneLite's stable per-account identifier. Nullable until the first
    # successful link-code exchange, unique once set so one game account
    # can't be linked to two myscape game accounts.
    account_hash = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Three more player-state snapshots synced by the RuneLite plugin,
    # alongside bank/inventory/equipment/etc. below -- what Mindmaps'
    # goal-node auto-completion (see evaluate_completion in
    # app/mindmaps.py) checks green/blue/purple nodes against. Unlike
    # those item tables, each of these is always exactly one current
    # snapshot rather than many independent rows, so a JSONB column
    # here fits the same way GearSetup.equipment/inventory already
    # does (see that model's docstring), rather than three more
    # single-purpose tables.
    #
    # skills: {<skill name, lowercase>: {"level": int, "xp": int}} for
    # every one of the 24 real OSRS skills the plugin has reported at
    # least once (see SKILL_NAMES in app/mindmaps.py). Synced by POST
    # /api/players/me/skills, full replace.
    skills = Column(JSONB, nullable=False, default=dict)
    # completed_quests: a flat list of quest/miniquest names exactly as
    # RuneLite's own Quest enum names them (see MyscapePlugin#syncQuests
    # in the Mootrius/myscape-plugin repo), matched case-insensitively
    # against a blue goal node's chosen quest. Synced by POST
    # /api/players/me/quests, full replace.
    completed_quests = Column(JSONB, nullable=False, default=list)
    # in_progress_quests: same shape/naming as completed_quests above,
    # but for QuestState.IN_PROGRESS instead of FINISHED (see
    # MyscapePlugin#readInProgressQuestNames in the Mootrius/myscape-
    # plugin repo) -- a quest/miniquest name in neither this list nor
    # completed_quests reads as "not started". Added for Character
    # Overview's quest section (render_character_overview in
    # app/pages.py), which needs this third state to color a quest
    # red/yellow/green rather than just done/not-done. Synced
    # alongside completed_quests by the same POST
    # /api/players/me/quests, full replace.
    in_progress_quests = Column(JSONB, nullable=False, default=list)
    # diary_tiers: {<diary area name, lowercase>: <highest tier
    # completed, one of DIARY_TIERS in app/mindmaps.py>} -- only the
    # highest tier is kept per area (finishing Elite implies Hard/
    # Medium/Easy are done too), matching how the in-game diary journal
    # itself only ever shows one current tier per area. Synced by POST
    # /api/players/me/diaries, full replace.
    diary_tiers = Column(JSONB, nullable=False, default=dict)

    # collection_log_items: {<item id, as a string -- JSONB object keys
    # are always strings>: <quantity>} for every collection log item
    # the player has actually obtained, however many are currently
    # captured -- NOT one entry per item the schema knows about (see
    # app/collectionlog.py's own get_valid_item_ids/get_collection_log_
    # tabs for the full, static, every-player-identical structure this
    # is checked against and rendered alongside). An item id simply
    # missing from this dict means "not yet obtained", the same way an
    # area missing from diary_tiers above means "no tier complete yet"
    # -- there's no separate boolean, the presence of the key IS the
    # obtained flag. Synced by POST /api/players/me/collection-log,
    # full replace -- see CollectionLogItemCapture in the
    # Mootrius/myscape-plugin repo for how the plugin actually gets
    # this data at all (it isn't cache data the way the schema
    # structure is; the collection log widget has to actually be
    # opened in-game).
    collection_log_items = Column(JSONB, nullable=False, default=dict)
    # When collection_log_items above was last synced -- null until the
    # player has opened the collection log widget in-game at least once
    # with the plugin running, same "never synced" meaning as
    # hiscores_synced_at below rather than storage_synced_at's own
    # per-key dict (there's only one thing to track here, not fourteen).
    collection_log_synced_at = Column(DateTime(timezone=True), nullable=True)

    # storage_synced_at: {<storage key>: <ISO 8601 timestamp>} for every
    # one of the fourteen sources Storages Viewer's side-panel
    # Status section reports on -- "bank", "equipment", "inventory",
    # "potion_storage", "rune_pouch", "seed_vault", "looting_bag",
    # "tackle_box", "poh", "forestry_kit", "master_scroll_book",
    # "seed_box", "huntsmans_kit", "boat_cargo" -- stamped every time
    # that source's own sync endpoint is hit (see each POST
    # /api/players/me/<source> handler in
    # app/main.py), full replace of just that one key rather than the
    # whole dict.
    #
    # Deliberately its own column rather than inferred from the item
    # tables' own updated_at columns: a storage that syncs as
    # genuinely EMPTY (an unstocked rune pouch, a bare bank) leaves
    # zero rows behind, and BankOut/InventoryOut/etc.'s own
    # `updated_at = items[0].updated_at if items else None` already
    # reads that indistinguishably from "never synced at all" -- see
    # those GET handlers in app/main.py. This column answers "has the
    # plugin told us about this source at least once" on its own,
    # independent of whatever that source currently holds.
    storage_synced_at = Column(JSONB, nullable=False, default=dict)

    # Cached boss-kill-count snapshot from the official OSRS Hiscores
    # (see app/hiscores.py) -- {<boss name, matching
    # app.bosses.HISCORE_BOSSES>: <kill count>}. This IS what Goal
    # Tracking's KC column displays directly (render_goal_tracking in
    # app/pages.py reads player.boss_kill_counts as-is, no further
    # merging) -- unlike skills/completed_quests/diary_tiers above, it's
    # written from two different places rather than one: seeded by a
    # one-time hiscores pull the moment this account links or re-links
    # (exchange_link_code in app/routers/linking.py, via
    # app.hiscores.sync_hiscores), then kept current from there by the
    # plugin's own live chatbox-parsed updates (POST
    # /api/players/me/kill-counts, via
    # app.hiscores.apply_kill_count_updates, the instant it reads a
    # "Your <boss> kill count is: <n>." style message). Every boss the
    # hiscores currently track is a key once the first sync has run (0
    # for "never killed it", not omitted -- see _parse_boss_kill_counts
    # in app/hiscores.py), so an empty dict unambiguously means "never
    # linked/synced" rather than "synced, ranked for nothing"; once
    # populated, a boss with no chatbox update yet just keeps whatever
    # the hiscores baseline said, which is why the table can look
    # "partially fresh" in perfectly ordinary use.
    #
    # No interval polling writes this any more, and there's
    # deliberately no diffing against a previous value either: a
    # hiscores pull only ever fires at a moment (link/relink, or the
    # manual /api/players/me/hiscores/sync escape hatch) where trusting
    # it outright is correct, and a chatbox update IS the ground truth
    # the instant the game reports it -- see app/hiscores.py's own
    # top-of-file comment for the fuller design discussion, including
    # the one real tradeoff this accepts (a dropped chat message has no
    # self-correction until the next hiscores pull).
    boss_kill_counts = Column(JSONB, nullable=False, default=dict)
    # {<boss name>: <ISO timestamp>} -- when boss_kill_counts[name]
    # above was last written, whether by the link-time hiscores
    # baseline or a live chatbox update, one entry per boss once that
    # boss has been seen at least once. Purely informational for now
    # (no reader depends on it the way the interval-polling design's
    # display_boss_kill_counts once did) -- kept as a per-boss "as of
    # when is this number good" record, e.g. for a future goal-progress
    # UI that wants to say how fresh a given boss's count is.
    boss_kill_counts_updated_at = Column(JSONB, nullable=False, default=dict)
    # Cached clue-tier completion-count snapshot from the same hiscores
    # pull that populates boss_kill_counts above -- {<hiscores clue-tier
    # name, one of app.bosses.CLUE_SCROLL_HISCORE_NAMES>: <completion
    # count>}. Written only by app.hiscores.sync_hiscores (see
    # _parse_clue_scroll_counts there); unlike boss_kill_counts there's
    # no live chatbox-parsed update path for this -- RuneLite doesn't
    # announce a running clue-completion count the way it does a kill
    # count -- so this is only ever as fresh as hiscores_synced_at
    # below, with no per-tier anchor column of its own needed. Read by
    # app.bosses.collection_log_page_kill_counts (via
    # read_collection_log in app/main.py) to show a completion count
    # above a clue-tier page's own item grid, the same way
    # boss_kill_counts feeds a boss page's count.
    clue_scroll_counts = Column(JSONB, nullable=False, default=dict)
    # Which hiscores game-mode endpoint actually resolved this account
    # (one of app.hiscores.GAMEMODES' first elements) -- cached after
    # the first successful sync purely so every later one hits that
    # endpoint directly instead of probing every game mode again. Null
    # until the first successful sync.
    hiscores_account_type = Column(String, nullable=True)
    # When the hiscores were last successfully FETCHED via
    # app.hiscores.sync_hiscores -- link/relink time, or a manual
    # /api/players/me/hiscores/sync call; NOT touched by a live chatbox
    # update (see apply_kill_count_updates, which only ever writes
    # boss_kill_counts/boss_kill_counts_updated_at above). Mostly
    # relevant to sync_hiscores's own short anti-rapid-fire cooldown
    # now (_MIN_ACCOUNT_REFRESH_SECONDS) rather than anything Goal
    # Tracking's UI reads directly any more.
    hiscores_synced_at = Column(DateTime(timezone=True), nullable=True)
    # Which of Goal Tracking's own #gtSortTabs buttons is active (see
    # app.goals.GOAL_SORT_MODES) -- one value per account, not per-goal,
    # since the whole list shares one sort at a time, same reasoning
    # GearSetup.still_to_purchase_sort_mode already applies one level
    # down (per setup instead of per account). Always a real value
    # ("alphabetical" for a fresh account, same default the goal list
    # always sorted by before this column existed), never null, so the
    # UI never has to guess what an unset preference means.
    goal_sort_mode = Column(String, nullable=False, default="alphabetical")

    # Character Overview's summary row (POST
    # /api/players/me/character-summary) -- the seven stats the
    # myscape-plugin repo reads straight off the in-game "Character
    # Summary" tab (InterfaceID.AccountSummarySidepanel), since none of
    # them are derivable from anything else this app already syncs (see
    # that endpoint's own docstring in app/main.py). All eight are null
    # until the player has actually opened that tab at least once with
    # the plugin running -- render_character_overview (app/pages.py)
    # treats a null the same way every other never-synced stat in this
    # app is treated, an em dash rather than a wrong number. Unlike
    # skills/completed_quests/diary_tiers above, none of these seven has
    # a companion "current progress" UI that would need incremental
    # per-field updates -- each sync fully replaces all seven together,
    # since the plugin always reads (and the endpoint always sends) the
    # whole panel in one pass.
    #
    # questsCompleted/questsTotal stands in for quest points -- the
    # panel itself doesn't surface a raw QP number, only this completion
    # count (see MyscapeClient.CharacterSummaryItem's own doc in the
    # Mootrius/myscape-plugin repo).
    character_summary_combat_level = Column(Float, nullable=True)
    character_summary_total_level = Column(Integer, nullable=True)
    # BigInteger, not Integer: a maxed account's total XP (24 skills x
    # 200M cap each) comfortably exceeds Integer's ~2.1 billion ceiling.
    character_summary_total_xp = Column(BigInteger, nullable=True)
    character_summary_quests_completed = Column(Integer, nullable=True)
    character_summary_quests_total = Column(Integer, nullable=True)
    character_summary_achievements_completed = Column(Integer, nullable=True)
    character_summary_achievements_total = Column(Integer, nullable=True)
    character_summary_combat_tasks_completed = Column(Integer, nullable=True)
    character_summary_combat_tasks_total = Column(Integer, nullable=True)
    character_summary_collections_completed = Column(Integer, nullable=True)
    character_summary_collections_total = Column(Integer, nullable=True)
    # character_summary_combat_task_tier_completed: {<tier, one of
    # "easy"/"medium"/"hard"/"elite"/"master"/"grandmaster">:
    # <completed task count>} -- the same six combat-achievement-tier
    # varbits character_summary_combat_tasks_completed above is their
    # SUM of, kept separate here instead (see MyscapePlugin#
    # patchCombatAchievementStats in the Mootrius/myscape-plugin repo).
    # Null until the first sync that includes it, same "never synced"
    # meaning every other character_summary_* field uses -- Character
    # Overview's combat achievements section (render_character_overview
    # in app/pages.py) pairs each tier's count here against that fixed
    # tier's own total task count (app.character_progress_data.
    # get_ca_tier_totals), which is static game content, not something
    # synced from the plugin at all.
    character_summary_combat_task_tier_completed = Column(JSONB, nullable=True)
    character_summary_synced_at = Column(DateTime(timezone=True), nullable=True)

    # The player's current 3D model export (POST
    # /api/players/me/character-model) -- a single self-contained .glb
    # (glTF 2.0 binary) file, the local player's composited mesh (base
    # skeleton + every equipped item + current animation pose) exactly
    # as RuneLite's own Renderable#getModel() hands it to the client's
    # renderer, converted client-side by the myscape-plugin repo's
    # io.myscape.plugin.modelexport package (ModelMeshBuilder + GlbWriter)
    # and sent up whole. Stored as bytes directly on this row rather
    # than on disk (see app/icon_cache.py's own docstring for why a
    # local disk cache is a bad fit for this single free-tier Render
    # web service -- no persistent disk actually mounted there yet,
    # see render.yaml -- so anything written to local disk is gone on
    # the next deploy/restart) -- Postgres already holds everything
    # else this app persists, and one player's own model export is a
    # small enough blob (a single composited player model, typically
    # well under a megabyte) that BYTEA storage here is simpler than
    # standing up a separate object-storage integration for it. Full
    # replace, same as every other current-state sync -- there's only
    # ever one "current" model per account, not a history of captures.
    # Null until the player has actually clicked "Export 3D model" in
    # the plugin's side panel at least once; the Character Overview
    # viewer (GET /api/character-overview/model) treats that the same
    # way every other never-synced value on that page is treated --
    # nothing to show yet, not a broken viewer.
    character_model_glb = Column(LargeBinary, nullable=True)
    character_model_synced_at = Column(DateTime(timezone=True), nullable=True)

    # The social/public-profile pair: whether this character's own
    # Character Overview is visible to anyone with the link, and the
    # link's own stable identifier. Deliberately per-GameAccount, not
    # per-Account -- an Account can link more than one OSRS character
    # (see this class's own docstring), and sharing one shouldn't force
    # the others public too. Defaults false/null for every character,
    # existing and new, so nothing becomes unexpectedly public on
    # deploy -- see migrations/versions for this pair's own migration.
    #
    # is_public_profile: a plain opt-in flag, flipped by POST
    # /api/players/me/public-profile. No "private but still has a
    # code" limbo state to worry about -- public_code below is
    # generated the first time this flips true (and kept afterward,
    # even if later flipped back false, so re-enabling doesn't hand
    # out a different link than whatever was already shared) rather
    # than cleared when this goes false.
    is_public_profile = Column(Boolean, nullable=False, default=False)
    # public_code: the 5-character, case-insensitive code in
    # myscape.io/c/<code> -- generated by generate_public_code in
    # app/public_profile.py (random from a visually-unambiguous
    # alphabet, checked against a blocklist and for collisions, never
    # derived from runescape_name) the first time is_public_profile is
    # set true, or by POST /api/players/me/public-profile/regenerate-
    # code on demand (e.g. a player wants to kill an already-shared
    # link without going private). Always stored lowercase -- see
    # normalize_public_code's own docstring for why lookups normalize
    # the same way rather than this column needing a separate
    # case-insensitive index. Null until the first time this account
    # ever goes public; never reused by another account once assigned,
    # even after this one goes private again, so an old shared link
    # never silently starts pointing at a different person.
    public_code = Column(String, nullable=True, unique=True)

    account = relationship("Account", back_populates="game_accounts")

    link_codes = relationship("LinkCode", back_populates="game_account", cascade="all, delete-orphan")
    api_keys = relationship("PlayerApiKey", back_populates="game_account", cascade="all, delete-orphan")
    bank_items = relationship("BankItem", back_populates="game_account", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="game_account", cascade="all, delete-orphan")
    equipment_items = relationship("EquipmentItem", back_populates="game_account", cascade="all, delete-orphan")
    potion_storage_items = relationship("PotionStorageItem", back_populates="game_account", cascade="all, delete-orphan")
    rune_pouch_items = relationship("RunePouchItem", back_populates="game_account", cascade="all, delete-orphan")
    seed_vault_items = relationship("SeedVaultItem", back_populates="game_account", cascade="all, delete-orphan")
    looting_bag_items = relationship("LootingBagItem", back_populates="game_account", cascade="all, delete-orphan")
    tackle_box_items = relationship("TackleBoxItem", back_populates="game_account", cascade="all, delete-orphan")
    poh_items = relationship("PohItem", back_populates="game_account", cascade="all, delete-orphan")
    forestry_kit_items = relationship("ForestryKitItem", back_populates="game_account", cascade="all, delete-orphan")
    master_scroll_book_items = relationship("MasterScrollBookItem", back_populates="game_account", cascade="all, delete-orphan")
    seed_box_items = relationship("SeedBoxItem", back_populates="game_account", cascade="all, delete-orphan")
    huntsmans_kit_items = relationship("HuntsmansKitItem", back_populates="game_account", cascade="all, delete-orphan")
    boat_cargo_items = relationship("BoatCargoItem", back_populates="game_account", cascade="all, delete-orphan")
    gear_setups = relationship("GearSetup", back_populates="game_account", cascade="all, delete-orphan")
    loot_events = relationship("LootEvent", back_populates="game_account", cascade="all, delete-orphan")
    mindmaps = relationship("MindMap", back_populates="game_account", cascade="all, delete-orphan")
    possession_trackers = relationship("PossessionTracker", back_populates="game_account", cascade="all, delete-orphan")
    pinned_possession_items = relationship("PinnedPossessionItem", back_populates="game_account", cascade="all, delete-orphan")
    hidden_loot_entries = relationship("HiddenLootEntry", back_populates="game_account", cascade="all, delete-orphan")
    hidden_possession_storages = relationship("HiddenPossessionStorage", back_populates="game_account", cascade="all, delete-orphan")
    possession_views = relationship("PossessionView", back_populates="game_account", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="game_account", cascade="all, delete-orphan")


class LinkCode(Base):
    """A short-lived, single-use code generated by the website for a
    signed-in player, to be pasted into the RuneLite plugin's settings.
    Only its hash is stored -- the raw code is shown to the player
    exactly once, at generation time, and never persisted or logged."""

    __tablename__ = "link_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    code_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    game_account = relationship("GameAccount", back_populates="link_codes")

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and _utcnow() < _as_aware_utc(self.expires_at)


class PlayerApiKey(Base):
    """The long-lived credential the plugin actually authenticates with
    on every request, obtained by exchanging a LinkCode exactly once.
    Only its hash is stored. Revocable independently of the player ever
    generating a new link code (e.g. if a key leaks, revoke just it)."""

    __tablename__ = "player_api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    game_account = relationship("GameAccount", back_populates="api_keys")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class PasswordResetToken(Base):
    """A short-lived, single-use token emailed to a player who asked to
    reset their password (see POST /api/auth/forgot-password in
    app/routers/auth.py). Same shape and same reasoning as LinkCode
    above -- only its hash is stored, the raw token only ever exists in
    the email itself and the URL the player clicks from it -- just with
    its own, longer lifetime (see PASSWORD_RESET_TOKEN_LIFETIME) since
    it has to survive an actual email delivery rather than an
    instant on-screen copy/paste."""

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    account = relationship("Account", back_populates="password_reset_tokens")

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and _utcnow() < _as_aware_utc(self.expires_at)


class EmailVerificationToken(Base):
    """A short-lived, single-use token emailed to a player to confirm
    they actually control the address they signed up (or later changed
    their email to -- though there's no "change email" feature yet).
    Same shape and reasoning as PasswordResetToken above, right down to
    only ever storing its hash -- see EMAIL_VERIFICATION_TOKEN_LIFETIME
    for why its lifetime is longer."""

    __tablename__ = "email_verification_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    account = relationship("Account", back_populates="email_verification_tokens")

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and _utcnow() < _as_aware_utc(self.expires_at)


class BankItem(Base):
    """The player's current bank contents, as last reported by the
    RuneLite plugin (see POST /api/players/me/bank in main.py, and
    MyscapeClient#syncBank in the Mootrius/myscape-plugin repo). This is
    always a full snapshot of "what's in the bank right now", not a
    history -- every sync deletes the player's existing rows and
    replaces them with exactly what the request says, so an item
    that's been sold or withdrawn since the last sync disappears from
    here too, the same as it disappeared from the actual bank. (A
    history of bank contents over time might be worth adding later, but
    Purchase Goals -- "do they currently have this?" -- only needs the
    present state.)

    item_id is OSRS's own item ID (what the plugin reads directly off
    each bank slot), not a foreign key to anything in this database --
    a *tradeable* item's name/icon/price are looked up separately (from
    the OSRS Wiki/GE API) rather than duplicated here, so this table
    doesn't need updating every time an item's price changes or a new
    item is released.

    item_name exists only for the untradeable case: an item with no GE
    listing has no entry in that wiki price/mapping data at all, so
    there's nothing to look its name up from server-side. It's what lets
    Purchase Goals recognize "you already own this" for an untradeable
    item typed into a gear-setup slot (which, having no GE listing
    either, was never given a real item_id to match against -- see
    _take_owned's name-fallback path in app/purchase_goals.py) --
    exactly the role Maintrius's own totalsByName played, just sourced
    from this plugin's ItemManager lookup instead of a third-party
    exporter plugin's JSON export. Sent for every item regardless of
    tradeability (simpler than the plugin having to know which is
    which), but only ever read back for the untradeable, no-item_id-
    match case.
    """

    __tablename__ = "bank_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="bank_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_bank_items_game_account_item"),)


class InventoryItem(Base):
    """The player's current main-inventory contents (the 28-slot
    backpack, not the bank) -- same full-snapshot, delete-and-replace
    model as BankItem above, and for the same reason: Purchase Goals
    only needs "do they currently have this?", not a history. Synced by
    POST /api/players/me/inventory (see MyscapeClient#syncInventory in
    the Mootrius/myscape-plugin repo).

    Quantities here are already aggregated by item id on the plugin
    side (see MyscapePlugin#aggregateQuantities there) -- unlike a bank
    slot, an inventory slot commonly holds just 1 of an untradeable
    item, with the same item spread across several separate slots, so
    this table's quantity is a real sum across however many slots held
    it, not a single slot's own count.

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "inventory_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="inventory_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_inventory_items_game_account_item"),)


class EquipmentItem(Base):
    """The player's currently worn equipment -- one row per filled
    equipment slot (head/cape/neck/weapon/body/shield/legs/hands/boots/
    ring/ammo, matching the original Maintrius tool's own EQUIPMENT_SLOTS),
    not aggregated by item id the way bank/inventory are, since exactly
    one item can ever occupy a given slot. Same full-snapshot,
    delete-and-replace model as BankItem/InventoryItem, synced by POST
    /api/players/me/equipment (see MyscapeClient#syncEquipment in the
    Mootrius/myscape-plugin repo).

    quantity is almost always 1 -- present mainly for a stacked ammo
    slot (e.g. a stack of rune arrows). item_name plays the same
    untradeable-item-matching role documented on BankItem above."""

    __tablename__ = "equipment_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    slot = Column(String, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="equipment_items")

    __table_args__ = (UniqueConstraint("game_account_id", "slot", name="uq_equipment_items_game_account_slot"),)


class PotionStorageItem(Base):
    """The player's current Player-Owned-House Potion Storage contents
    -- same full-snapshot, delete-and-replace model as Bank/Inventory/
    EquipmentItem above. Synced by POST /api/players/me/potion-storage
    (see MyscapeClient#syncPotionStorage in the Mootrius/myscape-plugin
    repo).

    This closes the gap the old "supplies" gear-slot flag used to paper
    over: potions kept in the Costume Room's Potion Storage were
    previously invisible to this plugin entirely (it only ever read
    the bank/inventory/equipment ItemContainers, and Potion Storage
    isn't one), so a gear slot needing a potion could never actually be
    recognized as owned even when it was, sitting safely in storage.
    "Supplies" worked around that by letting a slot be marked
    always-owned regardless of what was actually held. Now that the
    plugin reads Potion Storage directly (see
    MyscapePlugin#readPotionStorageItems there, which decomposes the
    stored dose totals into real item ids the same way withdrawing them
    would), that workaround is gone and potions are matched for real,
    the same as everything else -- see _build_owned_pools in
    app/purchase_goals.py, which folds this table into the same pool as
    bank/inventory/equipment with no special-casing needed.

    item_name plays the same untradeable-item-matching role documented
    on BankItem above, even though every potion item id is itself
    GE-tradeable in practice -- kept for consistency with the other
    three tables rather than because it's ever actually needed here."""

    __tablename__ = "potion_storage_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="potion_storage_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_potion_storage_items_game_account_item"),)


class RunePouchItem(Base):
    """The player's current Rune Pouch contents -- same full-snapshot,
    delete-and-replace model as Bank/Inventory/Equipment/
    PotionStorageItem above. Synced by POST /api/players/me/rune-pouch
    (see MyscapeClient#syncRunePouch in the Mootrius/myscape-plugin
    repo).

    A Rune Pouch (regular or Divine) is a single inventory item whose
    contents RuneLite can't read as part of a normal inventory scan --
    the pouch itself shows up as one InventoryItem entry, but the runes
    held inside it are exposed only through a separate set of varbits
    (see MyscapePlugin#readRunePouchItems there). Before this table
    existed, those runes were invisible to Purchase Goals entirely: the
    plugin only ever read the bank/inventory/equipment/potion-storage
    sources, and a rune pouch's contents fit none of them, so a setup
    needing (for example) fire runes would keep listing them as still
    to buy even while a full pouch of them sat in the player's own
    inventory.

    Deliberately its own table rather than folded into
    InventoryItem's payload: /api/players/me/inventory caps the number
    of *distinct* item entries per sync (MAX_INVENTORY_ITEMS), and a
    stocked pouch can add several more distinct entries on top of an
    otherwise-normal inventory -- routing it through its own endpoint,
    the same way Potion Storage already does, means a full pouch can
    never cause an otherwise-valid inventory sync to be rejected.

    See _build_owned_pools in app/purchase_goals.py, which folds this
    table into the same owned-item pool as bank/inventory/equipment/
    potion-storage with no special-casing needed.

    item_name plays the same untradeable-item-matching role documented
    on BankItem above -- kept for consistency, even though every rune
    is itself GE-tradeable in practice."""

    __tablename__ = "rune_pouch_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="rune_pouch_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_rune_pouch_items_game_account_item"),)


class SeedVaultItem(Base):
    """The player's current Player-Owned-House Seed Vault contents --
    same full-snapshot, delete-and-replace model as Bank/Inventory/
    Equipment/PotionStorage/RunePouchItem above. Synced by POST
    /api/players/me/seed-vault (see MyscapeClient#syncSeedVault in the
    Mootrius/myscape-plugin repo).

    Closes the same kind of gap PotionStorageItem/RunePouchItem already
    closed: the Seed Vault is its own container, not part of the normal
    bank/inventory/equipment ItemContainers RuneLite exposes, so seeds
    kept there were previously invisible to both Purchase Goals and an
    item-goal Mindmap node counting how many of a seed the player owns.

    item_name plays the same untradeable-item-matching role documented
    on BankItem above, even though nearly every seed is itself
    GE-tradeable in practice -- kept for consistency with every other
    item-source table."""

    __tablename__ = "seed_vault_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="seed_vault_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_seed_vault_items_game_account_item"),)


class LootingBagItem(Base):
    """The player's current Looting Bag contents -- same full-snapshot,
    delete-and-replace model as Bank/Inventory/Equipment/PotionStorage/
    RunePouch/SeedVaultItem above. Synced by POST
    /api/players/me/looting-bag (see MyscapeClient#syncLootingBag in
    the Mootrius/myscape-plugin repo).

    Unlike Potion Storage/Rune Pouch/Seed Vault, a Looting Bag IS a
    normal ItemContainer RuneLite exposes directly (InventoryID.
    LOOTING_BAG) -- the same way Bank is -- but, also like Bank, it
    only reports real contents once the player has actually opened it
    at least once in the current session (see
    MyscapePlugin#readLootingBagItems there).

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "looting_bag_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="looting_bag_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_looting_bag_items_game_account_item"),)


class TackleBoxItem(Base):
    """The player's current Tackle Box contents -- same full-snapshot,
    delete-and-replace model as every other item-source table above.
    Synced by POST /api/players/me/tackle-box (see
    MyscapeClient#syncTackleBox in the Mootrius/myscape-plugin repo).

    Like Looting Bag/Seed Vault above, this is a genuine
    ItemContainer RuneLite exposes directly (InventoryID.TACKLE_BOX),
    read the same straightforward way Bank/Looting Bag are -- and, same
    caveat as those, it only reports real contents once the player has
    actually opened the Tackle Box at least once in the current session
    (see MyscapePlugin#readTackleBoxItems there).

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "tackle_box_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="tackle_box_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_tackle_box_items_game_account_item"),)


class PohItem(Base):
    """The player's current Player-Owned-House (PoH) Costume Room
    contents -- same full-snapshot, delete-and-replace model as every
    other item-source table above. Synced by POST /api/players/me/poh
    (see MyscapeClient#syncPoh in the Mootrius/myscape-plugin repo).
    Named "PoH" rather than "Costume Room" since that's the display
    label Storages Viewer's location filter groups this storage
    under -- there's only the Costume Room in it today, but "PoH" is
    the general house-storage bucket, not specifically about costumes.

    Originally modeled as six separate tables, one per piece of
    furniture (Magic Wardrobe, Armour Case, Fancy Dress Box, Toy Box,
    Treasure Chest, Magic Cape Rack) -- matching how RuneLite names the
    six InventoryID.POH_COSTUME_ROOM_* constants. Live testing (logging
    which ItemContainer actually fires when each piece is opened) showed
    that assumption no longer holds: every piece fires
    ItemContainerChanged on the exact same container id (33405 -- not
    any of those six named constants, and not InventoryID.POH_COSTUMES
    either; it looks like a runtime/script-assigned id rather than a
    fixed gameval one), with identical contents regardless of which
    piece was opened. Jagex's newer, consolidated Costume Room interface
    (InterfaceID.POH_COSTUMES) reads from one unified store, not six --
    this table reflects that (see MyscapePlugin#readPohItems there),
    same caveat as every single-container source above: it only reports
    real contents once the player has opened the Costume Room interface
    at least once in the current session.

    item_name plays the same untradeable-item-matching role documented
    on BankItem above -- relevant here specifically since many clue and
    holiday-event rewards are untradeable."""

    __tablename__ = "poh_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="poh_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_poh_items_game_account_item"),)


class ForestryKitItem(Base):
    """The player's current Forestry Kit contents -- same
    full-snapshot, delete-and-replace model as every other item-source
    table above. Synced by POST /api/players/me/forestry-kit (see
    MyscapeClient#syncForestryKit in the Mootrius/myscape-plugin repo).

    Unlike the PoH storages above, the Forestry Kit is a portable item
    the player carries (in the "PORTABLE" location group on Possessions
    Monitoring, not "PoH") rather than furniture -- but it's still a
    genuine ItemContainer RuneLite exposes directly (InventoryID.
    FORESTRY_KIT), read the same straightforward way Tackle Box is, and
    with the same caveat: it only reports real contents once the player
    has actually opened it at least once in the current session (see
    MyscapePlugin#readForestryKitItems there).

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "forestry_kit_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="forestry_kit_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_forestry_kit_items_game_account_item"),)


class MasterScrollBookItem(Base):
    """The player's current Master Scroll Book contents (the teleport
    scrolls stored inside it) -- same full-snapshot, delete-and-replace
    model as every other item-source table above. Synced by POST
    /api/players/me/master-scroll-book (see
    MyscapeClient#syncMasterScrollBook in the Mootrius/myscape-plugin
    repo). Like the Forestry Kit above, this is a portable carried item
    (Storages Viewer's "PORTABLE" location group), not PoH
    furniture.

    Unlike every other source in this file, there's no confirmed
    RuneLite InventoryID or InterfaceID for the Master Scroll Book's
    contents as of this table's creation -- research (the OSRS Wiki,
    RuneLite's gameval source) turned up nothing, and the Costume Room
    saga above (six assumed containers that turned out to be one
    dynamically-assigned id never even in RuneLite's gameval) is a
    fresh reminder not to guess one. This table and its sync endpoint
    exist so the plugin side has somewhere to send data to once
    MyscapePlugin#readMasterScrollBookItems' own temporary diagnostic
    (see its doc comment there) confirms the real container/interface
    id -- until then, this simply never receives a real sync.

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "master_scroll_book_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="master_scroll_book_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_master_scroll_book_items_game_account_item"),)


class SeedBoxItem(Base):
    """The player's current Seed Box contents -- same full-snapshot,
    delete-and-replace model as every other item-source table above.
    Synced by POST /api/players/me/seed-box (see
    MyscapeClient#syncSeedBox in the Mootrius/myscape-plugin repo).
    Like the Forestry Kit above, this is a portable carried item
    (Storages Viewer's "PORTABLE" location group), not PoH
    furniture -- distinct from SeedVaultItem above, which is the PoH
    Seed Vault, a separate storage the Seed Box doesn't replace.

    A genuine ItemContainer RuneLite exposes directly (InventoryID.
    SEED_BOX), read the same straightforward way Tackle Box is, and
    with the same caveat: it only reports real contents once the player
    has actually opened it at least once in the current session (see
    MyscapePlugin#readSeedBoxItems there).

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "seed_box_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="seed_box_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_seed_box_items_game_account_item"),)


class HuntsmansKitItem(Base):
    """The player's current Huntsman's Kit contents -- same
    full-snapshot, delete-and-replace model as every other item-source
    table above. Synced by POST /api/players/me/huntsmans-kit (see
    MyscapeClient#syncHuntsmansKit in the Mootrius/myscape-plugin repo).
    Like the Forestry Kit/Seed Box above, this is a portable carried
    item (Storages Viewer's "PORTABLE" location group), not PoH
    furniture.

    A genuine ItemContainer RuneLite exposes directly (InventoryID.
    HUNTSMANS_KIT), read the same straightforward way Tackle Box/
    Forestry Kit/Seed Box are, and with the same caveat: it only
    reports real contents once the player has actually opened it at
    least once in the current session (see
    MyscapePlugin#readHuntsmansKitItems there).

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "huntsmans_kit_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="huntsmans_kit_items")

    __table_args__ = (UniqueConstraint("game_account_id", "item_id", name="uq_huntsmans_kit_items_game_account_item"),)


class BoatCargoItem(Base):
    """The player's current cargo hold contents for ONE of their (up to
    five, at max Sailing level -- see the OSRS Wiki's "Boat" article)
    independently-owned boats -- same full-snapshot, delete-and-replace
    model as every other item-source table above, just scoped to one
    more column: `slot` (1-5), which boat this row belongs to. Synced
    by POST /api/players/me/boat-cargo/{slot}, one slot at a time (see
    MyscapeClient#syncBoatCargo in the Mootrius/myscape-plugin repo) --
    unlike PoH's Costume Room above, where six pieces of furniture all
    turned out to read from one shared, identical container, a boat's
    cargo genuinely is its own separate contents per boat, so merging
    every slot into one storage the way PoH does would silently lose
    (or cross-contaminate) whichever boats weren't the one just synced.
    Deleting and replacing only rows matching (game_account_id, slot) on each
    sync -- never every row for the player -- is what keeps a sync of
    the boat the player happens to be standing near from wiping out
    what's already known about their other boats.

    Rolled up into a single "boat_cargo" entry in
    GameAccount.storage_synced_at and Storages Viewer's own location
    groups/breakdowns regardless of slot (see POSSESSION_STORAGE_KEYS
    in app/schemas.py and STORAGE_SOURCES in app/possessions.py) --
    those only ever needed one row per physical *kind* of storage, the
    same simplification PoH's own single "poh" key already makes, and
    nothing currently reads `slot` back out at that level; it exists
    purely so a per-boat sync can target and replace only its own rows.

    A genuine ItemContainer RuneLite exposes directly, one distinct id
    per boat slot (InventoryID.SAILING_BOAT_1_CARGOHOLD through
    SAILING_BOAT_5_CARGOHOLD, all backed by the same InterfaceID.
    SAILING_BOAT_CARGOHOLD interface regardless of which boat opened
    it), read the same straightforward way every other single-container
    source above is, and with the same caveat: a given slot only
    reports real contents once the player has actually opened THAT
    boat's cargo hold at least once in the current session (see
    MyscapePlugin#readBoatCargoItems there).

    item_name plays the same untradeable-item-matching role documented
    on BankItem above."""

    __tablename__ = "boat_cargo_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    slot = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="boat_cargo_items")

    __table_args__ = (UniqueConstraint("game_account_id", "slot", "item_id", name="uq_boat_cargo_items_game_account_slot_item"),)


class GearSetup(Base):
    """A named, saveable equipment+inventory loadout the player is
    planning/saving toward -- the Purchase Goals feature, ported from
    the original single-user Maintrius tool's "gear setups" (see
    build_gear_setups in that repo's osrs_tracker.py). A player can have
    any number of these (Vorkath, Raids, a skilling setup, ...); each is
    checked off independently against the player's current bank+
    inventory+equipment+potion storage, not against each other, so the
    same owned item can cover more than one setup's need for it.

    `equipment` and `inventory` are stored as opaque JSON blobs rather
    than normalized rows, deliberately mirroring how Maintrius itself
    stores a setup (as a JSON file) -- a slot's contents are one of
    several different shapes (a plain tradeable item, an untradeable
    item, or a "combo" item composed of multiple parts; see
    _resolve_gear_slot_item in the original repo), which is exactly the
    kind of polymorphic, mostly-write-then-read-whole structure JSON
    suits better than a rigid table. All the actual pricing/ownership
    computation happens fresh on every read (see app/purchase_goals.py), not stored here -- these
    columns hold only what the player actually chose to put in each
    slot.

    `equipment` is a dict keyed by slot name (only filled slots are
    present) -- see GEAR_SETUP_EQUIPMENT_SLOTS in app/schemas.py for the
    full set of 19 keys it may use: the 11 real, RuneLite-reportable
    equipment slots plus 8 "misc" planning-only slots (runes for a rune
    pouch, teleports, or any other item a setup needs beyond its actual
    gear) that exist only here, never in the real equipment-sync table
    (see EquipmentItem below). `inventory` is a list of exactly 28
    entries, each either an item shape or null for an empty slot. `icon`
    is a purely cosmetic {"itemId": int|None, "itemName": str|None} pair
    (or null) representing the whole setup, unrelated to cost/ownership.

    IMPORTANT for anything that edits equipment/inventory in place:
    SQLAlchemy only detects a change to a JSONB column when a *new*
    object is assigned to the attribute (setup.equipment = {...}), not
    when an existing dict/list already loaded onto it is mutated
    in-place (setup.equipment["head"] = ... would silently fail to
    persist) -- every write in app/main.py builds a whole new dict/list
    and assigns it, rather than mutating the loaded one."""

    __tablename__ = "gear_setups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    icon = Column(JSONB, nullable=True)
    equipment = Column(JSONB, nullable=False, default=dict)
    inventory = Column(JSONB, nullable=False, default=lambda: [None] * 28)
    # How the "Still to Purchase" list on this setup is ordered --
    # "low_to_high"/"high_to_low"/"alphabetical"/"reverse_alphabetical"
    # are computed fresh on every read same as everything else here, but
    # "custom" needs somewhere to remember the player's own drag-and-drop
    # ordering between requests, hence still_to_purchase_custom_order
    # below. See _still_to_purchase_summary in app/purchase_goals.py for
    # how all of these are actually applied.
    still_to_purchase_sort_mode = Column(String, nullable=False, default="low_to_high")
    # A list of {"slotType": "equipment"|"inventory", "slot": <str|int>}
    # entries, in the order the player last dragged them into -- the
    # same slot-identity shape move_gear_slot_item's payload uses,
    # deliberately, since a "still to purchase" row IS a specific
    # equipment/inventory slot (see build_gear_setups). Null/missing
    # until the player actually reorders something in "custom" mode; a
    # pending item with no entry here (new, or reordering never
    # touched it) falls back to cost-ascending, same as "low_to_high".
    still_to_purchase_custom_order = Column(JSONB, nullable=True)
    # The player's own drag-and-drop order for their LIST of gear
    # setups (contrast still_to_purchase_custom_order above, which
    # orders the rows INSIDE one setup) -- nullable, and left NULL
    # until a player actually reorders something. build_gear_setups in
    # app/purchase_goals.py orders by this column first and created_at
    # second, so with every setup's sort_order still NULL (nothing
    # dragged yet), the created_at tiebreaker alone decides the order:
    # oldest first, newest last, the default. Reordering (see the
    # PUT /api/gear-setups/order route in app/main.py) always rewrites
    # every setup's sort_order to its plain position (0, 1, 2, ...) in
    # the new order, the same "just re-send the whole list" approach
    # still_to_purchase_custom_order itself uses, rather than fractional
    # single-row inserts.
    sort_order = Column(Float, nullable=True)

    game_account = relationship("GameAccount", back_populates="gear_setups")


class MindMap(Base):
    """A player-created goal/idea tree -- the Mindmaps feature. A player
    can have any number of these, same as GearSetup above, and for the
    same reason `nodes` is one opaque JSONB blob rather than a normalized
    child table: a mindmap is always read and written as a whole (open
    the editor -> load every node; add/recolor/delete a node -> load the
    current tree, mutate it, write the whole thing back), so there's no
    "just this one row" access pattern a real table would be earning its
    keep for, and a self-referencing node table would need its own
    recursive-delete logic in exchange for nothing this blob doesn't
    already give for free (see delete_node in app/mindmaps.py, which is
    just a plain filter over a Python list).

    `nodes` is a flat list of {"id": str, "parentId": str|None, "text":
    str, "color": str, "order": float} dicts -- not nested, so a node's
    position in the tree is entirely determined by its own parentId
    (None for the single root) rather than by where it sits in the list.
    `order` ranks a node among its own parent's other children (lower
    sorts first); see app/mindmaps.py for how add_node picks a new
    node's order when inserting it as a parent/child/sibling of an
    existing one, and for the fixed set of valid `color` values.

    All the tree-shape logic (inserting/deleting a node, keeping the
    single-root invariant) lives in app/mindmaps.py, not here -- same
    split as GearSetup/app/purchase_goals.py."""

    __tablename__ = "mindmaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    nodes = Column(JSONB, nullable=False, default=list)

    game_account = relationship("GameAccount", back_populates="mindmaps")


class Goal(Base):
    """The redesigned Goal Tracking page's own goal list -- a flat set
    of targets a player is actively working toward, each one a boss
    kill count, a skill level/xp, or an item quantity. Deliberately
    NOT built on MindMap's `nodes` JSONB blob above, even though
    app/mindmaps.py already implements six goal types (this feature's
    three plus gp/quest/diary) inside a node's own `goal` dict: unlike
    a mindmap (always read/written as a whole tree, see MindMap's own
    docstring for why THAT earns a blob), a goal here is created and
    deleted independently of any others -- there's a real "just this
    one row" access pattern a blob wouldn't serve as well, so this is
    a normal one-row-per-goal table instead. See app/goals.py for the
    validation and live progress-computation logic (nothing here is
    ever pre-computed or cached).

    goal_type is one of "kc" (a boss kill count), "skill" (a skill
    level or xp target), or "item" (an owned quantity of some item) --
    see app.goals.GOAL_TYPES. target_name means something different
    per type: the exact OSRS-hiscores boss display name (matching
    app.bosses.HISCORE_BOSSES) for "kc", the lowercase skill name
    (app.mindmaps.SKILL_NAMES) for "skill", or a free-text item name
    for "item" (resolved to a real item at read time via
    app.item_ids.find_item_ids, same as Purchase Goals and Mindmaps'
    own item goals already do -- not resolved/validated to a real item
    at creation time, since a name that doesn't resolve to an id can
    still match app.purchase_goals.build_owned_pools' name-keyed pool).

    metric is ONLY meaningful for a "skill" goal ("level" or "xp"; null
    for "kc"/"item") -- same "only this one type actually uses this
    column" shape hiscores_account_type and a few other nullable
    columns elsewhere in this file already have. A "kc" goal's real
    lifetime progress is read straight from
    GameAccount.boss_kill_counts (the hiscores-seeded, chatbox-kept-
    live column -- see app/hiscores.py) -- deliberately NOT
    app.mindmaps' own "kc" goal machinery, which counts raw LootEvent
    occurrences instead (see app/goals.py's own module docstring for
    why that's the wrong number for a lifetime-total goal).

    item_id is ONLY meaningful for an "item" goal -- the real numeric
    OSRS item id the player's search suggestion carried when they
    picked it (app.item_ids' own id space), captured purely so the
    goal list can show that item's actual RuneLite-CDN icon
    (item_icon_url, app/purchase_goals.py) instead of the generic
    item-goal badge. Play no part in progress computation at all --
    that still resolves entirely from target_name (see
    app.goals.absolute_value) -- so it's fine for this to be null (a
    goal predating this column, or a free-text name that never matched
    a search result).

    is_recurring/recur_interval/recur_unit/recur_period_start together
    make a "kc" or "skill" goal (the wizard never offers this for
    "item") repeat every recur_interval*recur_unit (e.g. every 1 WEEK)
    instead of tracking one lifetime total forever -- see
    app.goals.current_value/maybe_roll_recurring_period for the actual
    rollover logic. Every OTHER goal field above keeps its exact same
    meaning either way (target_value is still the number to reach --
    just per-period instead of lifetime-total for a recurring goal);
    these four columns are additive, not a parallel goal shape.

    recur_period_start is the only one of that group a recurring goal
    ever has written back to it after creation (see
    maybe_roll_recurring_period) -- when the CURRENT period began, so
    the period's own progress is always "absolute_value() now minus
    baseline_value" rather than a lifetime total (see that column's own
    docstring just below). Null for a non-recurring goal, set once at
    creation time to "now" for a recurring one -- see create_goal in
    app/main.py.

    baseline_value is this goal's own absolute_value() reading at
    whatever moment its progress started being measured FROM, so
    current_value() (app/goals.py) can read "how much has actually
    changed since then" instead of a lifetime total -- absolute_value()
    minus this, floored at 0. Two different goals end up needing that
    same "progress since a starting point" shape for two different
    reasons, so this one column serves both:
      - a RECURRING goal (is_recurring true) always has one -- see
        recur_period_start above; re-baselined every time
        maybe_roll_recurring_period rolls the period forward, so it's
        never more than one period stale.
      - a ONE-TIME "GAIN"-mode kc goal or xp-metric skill goal also
        gets one, captured once at creation and never touched again --
        see create_goal in app/main.py, and
        app.goals.target_mode_allows_gain for exactly which
        combinations this is offered for at all (a target LEVEL has no
        equivalent "gain" reading -- see that function's own comment --
        and an item's own owned quantity isn't a monotonic lifetime
        total the way kc/xp are, the same reasoning
        RECURRING_GOAL_TYPES already excludes "item" for). The wizard's
        own #gtTargetModeToggle (GAIN/REACH, app/pages.py) is what lets
        a player choose this for a one-time goal; REACH (this column
        left null) is every one-time goal's only reading before this
        toggle existed, and still is for anything the toggle doesn't
        cover.
    Both a "REACH"-mode one-time goal and an "item" goal leave this
    null -- current_value() falls straight back to absolute_value()
    whenever it's null, regardless of is_recurring, so those two cases
    need no special-casing of their own there at all."""

    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    goal_type = Column(String, nullable=False)
    target_name = Column(String, nullable=False)
    metric = Column(String, nullable=True)
    target_value = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=True)
    is_recurring = Column(Boolean, nullable=False, default=False)
    recur_interval = Column(Integer, nullable=True)
    recur_unit = Column(String, nullable=True)
    recur_period_start = Column(DateTime(timezone=True), nullable=True)
    baseline_value = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # The player's own drag-and-drop order for the goal list in
    # "custom" sort mode (GameAccount.goal_sort_mode == "custom") --
    # works exactly like GearSetup.sort_order/PossessionView.sort_order
    # (see either one's own docstring for the fuller writeup): nullable,
    # left NULL until a player actually reorders something, rewritten
    # to plain float positions (0.0, 1.0, 2.0, ...) on every reorder
    # (see PUT /api/goals/reorder in app/main.py) rather than fractional
    # single-row inserts. The client's own sortGoals falls back to
    # created_at (oldest first) for any goal whose sort_order is still
    # NULL, so a freshly created goal that's never been dragged lands
    # at the end of a custom order without needing this backfilled at
    # creation time. The list itself is never queried in this order
    # server-side -- GET /api/goals always returns it in plain
    # created_at order and the client re-sorts
    # locally per whichever #gtSortTabs mode is active, "custom"
    # included (see sortGoals in app/pages.py), the same as every
    # other sort mode that page offers.
    sort_order = Column(Float, nullable=True)

    game_account = relationship("GameAccount", back_populates="goals")


class LootEvent(Base):
    """One kill/casket-opening/pickpocket's worth of loot, synced by
    POST /api/players/me/loot (see MyscapeClient#syncLootEvent in the
    Mootrius/myscape-plugin repo) -- the data source behind the Loot
    Tracker feature (see app/loot.py).

    Structurally different from BankItem/InventoryItem/EquipmentItem/
    PotionStorageItem/RunePouchItem above: those are all "current state"
    snapshots the plugin re-sends in full and this app deletes-and-
    replaces on every sync. Loot events are a historical log instead --
    each row is one thing that already happened and is never replaced,
    so a sync here is an insert, not a replace. That also means a sync
    can't just be retried blindly the way a snapshot sync can (retrying
    a delete-and-replace is naturally idempotent; retrying an insert
    isn't) -- event_id exists specifically to make it idempotent anyway:
    the plugin generates a random id once, the moment the drop happens,
    and a sync that already has a matching (game_account_id, event_id) row is
    just skipped rather than double-counted, so a retried or
    double-submitted sync can never inflate a player's totals.

    source_type is RuneLite's own LootRecordType, lowercased ("npc",
    "player", "event", "pickpocket", "unknown") -- "event" covers clue
    scroll caskets and other non-NPC rewards. RuneLite's own bundled
    Loot Tracker plugin (the actual source of this data -- see
    MyscapePlugin#onLootReceived) still reports every clue casket's own
    LootReceived event with source_name as the bare word "Casket", with
    no tier -- a known, real limitation of that specific event, not a
    bug here. MyscapePlugin works around it independently, though,
    rather than relying on RuneLite to ever fix it: it detects a
    completed trail's own tier itself, off the chatbox's "You have
    completed N <tier> Treasure Trails." line, and relabels that
    casket's source_name "Clue Scroll (<Tier>)" before syncing it here
    whenever it manages to pair the two up in time (see
    onChatMessage/onLootReceived in the Mootrius/myscape-plugin repo,
    and app/loot.py's own module docstring for the tier-scoped "Clue
    Scrolls" breakdown this makes possible server-side). Still just the
    bare "Casket", untiered, for any event synced before that plugin
    update existed, or the rarer case where the two couldn't be paired
    in time.

    items is a list of {"item_id": int, "item_name": str|None,
    "quantity": int} -- same shape as the other item-source tables'
    columns, just nested here as JSON per-event instead of one row per
    item, since a loot event's items are logically one unit (one kill's
    drops) rather than each contributing independently to a current-
    ownership pool the way bank/inventory items do."""

    __tablename__ = "loot_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    event_id = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    combat_level = Column(Integer, nullable=True)
    items = Column(JSONB, nullable=False, default=list)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="loot_events")

    __table_args__ = (UniqueConstraint("game_account_id", "event_id", name="uq_loot_events_game_account_event"),)


class PossessionTracker(Base):
    """One "keep an eye on this item" tracker for the Possessions
    Monitoring feature (see app/possessions.py) -- either a MINIMUM
    tracker (section 1: "I want at least `target_quantity` of this at
    all times", shown as a fill-toward-target progress bar -- e.g. 100
    of each herb for emergency potion-making) or a MAXIMUM tracker
    (section 2: "flag me once I have more than `target_quantity` of
    this, so I know to sell the excess", shown as a red/green box --
    e.g. 10,000 blood runes). Both are the same shape (an item plus one
    threshold), just read in opposite directions -- `kind` is what
    tells app/possessions.py and the page's own script which direction
    to evaluate and how to color it, rather than two separate tables
    for what's otherwise identical data.

    item_id is OSRS's own real item id -- see BankItem's docstring in
    this file for why that's what every owned-quantity source here is
    already keyed by, and item_name plays the same untradeable-item-
    display-fallback role documented there, used only when a live
    icon/name lookup (tradeable wiki mapping or the item_ids.json
    snapshot -- see app/possessions.py's search_trackable_items) comes
    up empty, e.g. an item the wiki/snapshot data hasn't caught up to
    yet.

    Current quantity is never stored here -- it's always computed live
    from whichever of bank/inventory/equipment/potion_storage/
    rune_pouch/seed_vault/looting_bag the tracker's own item_id is
    found in (see get_owned_quantity_map in app/possessions.py), the
    same "read the last-synced snapshot fresh every time" approach
    Purchase Goals already uses -- a tracker just remembers WHAT to
    watch and WHAT threshold matters, not a cached amount that could
    drift stale.

    sort_order works exactly like MindMap node ordering (see that
    model's own docstring) -- a float so a tracker can be inserted
    between two existing ones without renumbering every row after it;
    lower sorts first within its own `kind`."""

    __tablename__ = "possession_trackers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)  # "min" or "max"
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    target_quantity = Column(Integer, nullable=False)
    sort_order = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="possession_trackers")

    __table_args__ = (
        UniqueConstraint("game_account_id", "kind", "item_id", name="uq_possession_trackers_game_account_kind_item"),
    )


class PinnedPossessionItem(Base):
    """One item a player has pinned to the top of Possessions
    Monitoring's section 3 list (see build_possessions_summary/
    pinned_item_ids in app/possessions.py, and the pin button on each
    row in render_possessions, app/pages.py) -- purely a "float this to
    the top, separated from the rest" marker, nothing to configure
    about it beyond existing, unlike PossessionTracker above (no
    kind/threshold, so no item_name fallback either: a pinned item is
    only ever created from a row already on screen, which already has
    a name/icon resolved, so there's nothing to look up from an id
    alone the way an untradeable tracker target typed in by hand might
    need).

    item_id is the same OSRS real item id every other owned-quantity
    source in this file is keyed by (see BankItem's docstring) -- with
    one wrinkle inherited from the list it pins into, not introduced
    here: a merged potion-dose row's itemId is normally the stable
    "(1)-dose" item id regardless of which doses are actually owned
    (see _resolve_dose1_display in app/possessions.py), so a pin on one
    of those survives fine across syncs; only in the rare case that
    lookup fails does that row's id drift with whichever dose happens
    to be owned, which would just as quietly stop matching a pin here
    as it would anything else keyed off that id."""

    __tablename__ = "pinned_possession_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    item_id = Column(Integer, nullable=False)
    pinned_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="pinned_possession_items")

    __table_args__ = (
        UniqueConstraint("game_account_id", "item_id", name="uq_pinned_possession_items_game_account_item"),
    )


class HiddenLootEntry(Base):
    """One NPC or item a player has hidden from Loot Tracker (see
    app/loot.py's build_loot_state, which reads this table to strip a
    hidden NPC's kills/value out of the chart and header totals
    entirely, and to subtract a hidden item's value out of any NPC/
    window total it would otherwise count toward) -- the eye-icon
    button on each NPC/item tile in render_loot_tracker, app/pages.py.

    Both kinds share one table (kind="npc"/"item") rather than two,
    since neither needs any column the other doesn't and a single
    "is this key hidden" lookup covers both call sites in
    build_loot_state identically.

    `key` is a case-insensitive identity string, never the raw display
    name/id alone, so a hide made against one casing of an NPC name
    (or made before an item's own name was known) still matches later:
    an NPC's key is just its lowercased, trimmed sourceName (loot
    events carry no numeric NPC id to key off instead); an item's key
    is "id:<itemId>" when the drop resolved to a real item id, else
    "name:<lowercased itemName>" for the rare drop that never
    resolved one -- the exact same two-tier fallback
    _add_item_totals already keys its own per-item totals dicts by
    (see loot_hide_key in app/loot.py, the single place both this
    table's writes and build_loot_state's reads compute that key, so
    the two can never drift apart)."""

    __tablename__ = "hidden_loot_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    key = Column(String, nullable=False)
    hidden_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="hidden_loot_entries")

    __table_args__ = (
        UniqueConstraint("game_account_id", "kind", "key", name="uq_hidden_loot_entries_game_account_kind_key"),
    )


class HiddenPossessionStorage(Base):
    """One storage source a player has switched off in Possessions
    Monitoring's settings menu (see hidden_storage_keys/
    set_storage_hidden in app/possessions.py, and the gear-icon menu
    next to the location filter buttons in render_possessions,
    app/pages.py) -- purely an on/off marker, same "presence of the
    row is the whole state" shape as HiddenLootEntry above: a row
    existing means that storage's items are hidden from section 3's
    list (and from every min/max tracker's owned-quantity count,
    since both read the same get_owned_breakdown); no row for a given
    (player, storage_key) means shown, which is why nothing needs to
    be created for a brand new player before every storage reads as
    "on" by default.

    storage_key is one of POSSESSION_STORAGE_KEYS (app/schemas.py) --
    the same raw per-source key spelling as STORAGE_SOURCES in
    app/possessions.py, BankItem and friends' own game_account_id-scoped
    tables, and the plugin panel's own Status section list -- never
    one of render_possessions' five grouped filter-button labels
    (BANK, CHARACTER, ...), which stay a purely client-side grouping
    of these same raw keys and know nothing about this table."""

    __tablename__ = "hidden_possession_storages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    storage_key = Column(String, nullable=False)
    hidden_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="hidden_possession_storages")

    __table_args__ = (
        UniqueConstraint("game_account_id", "storage_key", name="uq_hidden_possession_storages_game_account_key"),
    )


class PossessionView(Base):
    """A named, saved filter+sort configuration for Storages Viewer's
    full raw list (section 3 -- see build_possession_views/
    build_possessions_summary in app/possessions.py, and the saved-
    views strip above the table headers in render_possessions,
    app/pages.py) -- lets a player switch between several different
    ways of looking at the same underlying item list (e.g. "high value
    junk to sell" vs. "untradeables I'm hoarding") without re-setting
    up the same column filters and sort by hand every time.

    `config` is one opaque JSON blob -- {"sortKey", "sortDir",
    "filters": {...}} -- rather than a column per filterable field,
    same reasoning as GearSetup's own equipment/inventory columns (see
    that model's docstring): the exact filter shape is owned and
    interpreted entirely by render_possessions' own script, which is
    still evolving, and the server only ever stores and returns this
    blob whole, never reads inside it.

    sort_order works exactly like GearSetup's own list-reorder column
    (see that model's docstring for the fuller writeup) -- nullable,
    rewritten to plain integer positions (0, 1, 2, ...) on every
    reorder (see PUT /api/possessions/views/order in app/main.py)
    rather than fractional single-row inserts."""

    __tablename__ = "possession_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    config = Column(JSONB, nullable=False, default=dict)
    sort_order = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="possession_views")
