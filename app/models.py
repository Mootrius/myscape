"""SQLAlchemy models.

Account linking is a two-phase handoff with the RuneLite plugin: a
short-lived, single-use LINK CODE from the website is exchanged once for a
long-lived, revocable API KEY used for every upload. Only SHA-256 hashes of
both are stored. Game accounts are bound to RuneLite's stable `account_hash`,
not the mutable display name.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base

LINK_CODE_LIFETIME = timedelta(minutes=10)
# Longer than LINK_CODE_LIFETIME: the token has to survive an email arriving,
# but a stale reset link should not stay valid for days.
PASSWORD_RESET_TOKEN_LIFETIME = timedelta(hours=1)

# Longer than PASSWORD_RESET_TOKEN_LIFETIME: email confirmation is lower-stakes
# and easy to put off.
EMAIL_VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)


def _utcnow():
    return datetime.now(timezone.utc)


def _as_aware_utc(value):
    """SQLite (local/dev) drops tzinfo on DateTime(timezone=True) columns, so a
    value read back can be naive. Treat naive values as UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class Account(Base):
    """The website login (email, password, verification state). One Account owns
    many GameAccounts (docs/multi-account-scoping.md).
    """

    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=True, unique=True)
    # Nullable only for rows created by admin tooling; the signup endpoint
    # always sets it.
    password_hash = Column(String, nullable=True)
    # Bumped on password reset. The session cookie (log_in_player, app/auth.py)
    # snapshots it and a mismatch logs that session out; sessions have no
    # server-side store, so this is the only way to revoke them.
    token_version = Column(Integer, nullable=False, default=0)
    # NULL until the emailed link is used (POST /api/auth/verify-email). Gates
    # most of the site (get_current_verified_player_from_session, app/auth.py).
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    game_accounts = relationship("GameAccount", back_populates="account", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="account", cascade="all, delete-orphan")
    email_verification_tokens = relationship("EmailVerificationToken", back_populates="account", cascade="all, delete-orphan")


class GameAccount(Base):
    """One linked OSRS character and everything the plugin reports for it. An
    Account can own several.
    """

    __tablename__ = "game_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    # Display name from the plugin. Mutable, so informational only; account_hash
    # is the identity.
    runescape_name = Column(String, nullable=True)
    # RuneLite's stable account identifier. Null until the first link-code
    # exchange; unique once set.
    account_hash = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Player-state snapshots from the plugin (full replace per sync), checked by
    # Mindmaps auto-completion (evaluate_completion, app/mindmaps.py).
    # skills: {<lowercase skill name>: {"level": int, "xp": int}}.
    skills = Column(JSONB, nullable=False, default=dict)
    # completed_quests: names as RuneLite's Quest enum names them, matched
    # case-insensitively.
    completed_quests = Column(JSONB, nullable=False, default=list)
    # in_progress_quests: same shape; a name in neither list is not started.
    in_progress_quests = Column(JSONB, nullable=False, default=list)
    # diary_tiers: {<lowercase area>: <highest completed tier (DIARY_TIERS)>}.
    diary_tiers = Column(JSONB, nullable=False, default=dict)
    # diary_task_counts: {<lowercase area>: {<tier (DIARY_TIERS)>: tasks
    # completed}}, from the plugin's per-tier task counts. Empty until the
    # plugin sends them (older plugin versions never do); diary_tiers alone
    # cannot show partial progress inside a tier.
    diary_task_counts = Column(JSONB, nullable=False, default=dict)

    # collection_log_items: {<item id as string>: <quantity>}, obtained items
    # only (missing key = not obtained).
    collection_log_items = Column(JSONB, nullable=False, default=dict)
    # Null until the collection log has been opened in-game.
    collection_log_synced_at = Column(DateTime(timezone=True), nullable=True)

    # storage_synced_at: {<storage key>: <ISO timestamp>} per Storages Viewer
    # source; each sync replaces only its own key. Separate from the item tables
    # because an empty storage leaves no rows, which would look like never
    # synced.
    storage_synced_at = Column(JSONB, nullable=False, default=dict)

    # boss_kill_counts: {<HISCORE_BOSSES name>: <kills>}. Seeded by a hiscores
    # pull at link/relink (app.hiscores.sync_hiscores), then kept current by
    # chatbox updates (apply_kill_count_updates). After the first sync every
    # boss is a key (0 if never killed), so an empty dict means never synced.
    # See the top of app/hiscores.py.
    boss_kill_counts = Column(JSONB, nullable=False, default=dict)
    # {<boss name>: <ISO timestamp>} of the last write to
    # boss_kill_counts[name].
    boss_kill_counts_updated_at = Column(JSONB, nullable=False, default=dict)
    # Clue-tier counts {<CLUE_SCROLL_HISCORE_NAMES name>: <count>}; written only
    # by sync_hiscores (no live update path).
    clue_scroll_counts = Column(JSONB, nullable=False, default=dict)
    # Hiscores game-mode endpoint that resolved this account
    # (app.hiscores.GAMEMODES), cached to skip probing.
    hiscores_account_type = Column(String, nullable=True)
    # Last hiscores fetch (not touched by chatbox updates); drives the sync
    # cooldown (_MIN_ACCOUNT_REFRESH_SECONDS).
    hiscores_synced_at = Column(DateTime(timezone=True), nullable=True)
    # Active Goal Tracking sort tab (app.goals.GOAL_SORT_MODES).
    goal_sort_mode = Column(String, nullable=False, default="alphabetical")

    # Character Overview summary stats (POST /api/players/me/character-summary),
    # read off the in-game Character Summary tab. Null until it has been opened;
    # each sync replaces all together. questsCompleted/questsTotal stand in for
    # quest points, which the panel does not expose.
    character_summary_combat_level = Column(Float, nullable=True)
    character_summary_total_level = Column(Integer, nullable=True)
    # BigInteger: a maxed account's total XP (24 x 200M) exceeds Integer's ~2.1
    # billion ceiling.
    character_summary_total_xp = Column(BigInteger, nullable=True)
    character_summary_quests_completed = Column(Integer, nullable=True)
    character_summary_quests_total = Column(Integer, nullable=True)
    character_summary_achievements_completed = Column(Integer, nullable=True)
    character_summary_achievements_total = Column(Integer, nullable=True)
    character_summary_combat_tasks_completed = Column(Integer, nullable=True)
    character_summary_combat_tasks_total = Column(Integer, nullable=True)
    character_summary_collections_completed = Column(Integer, nullable=True)
    character_summary_collections_total = Column(Integer, nullable=True)
    # {<easy|...|grandmaster>: <completed count>}; sums to
    # character_summary_combat_tasks_completed. Tier totals:
    # app.character_progress_data.get_ca_tier_totals.
    character_summary_combat_task_tier_completed = Column(JSONB, nullable=True)
    # account_type: MAIN, IRONMAN, UIM, HCIM, GIM, HCGIM or UGIM
    # (Varbits.ACCOUNT_TYPE 0-6, in that order). Sent with the character-summary
    # sync but a durable account property, hence unprefixed; also shown on
    # public profiles.
    account_type = Column(String, nullable=True)
    character_summary_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Current 3D model export (POST /api/players/me/character-model), one .glb.
    # Stored in Postgres because the Render service has no persistent disk
    # (app/icon_cache.py, render.yaml).
    character_model_glb = Column(LargeBinary, nullable=True)
    character_model_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Model-viewer background index (_MODEL_VIEWER_BACKGROUNDS, app/pages/).
    # The browser's localStorage is primary; this lets public-profile visitors
    # see the owner's choice. Null means 0.
    model_viewer_background_index = Column(Integer, nullable=True)

    # Public-profile pair, per GameAccount. Defaults false/null so nothing
    # becomes public on deploy. public_code is kept when the flag flips back to
    # false so re-enabling reuses the link.
    is_public_profile = Column(Boolean, nullable=False, default=False)
    # 5-character code in myscape.io/c/<code> (generate_public_code,
    # app/public_profile.py), stored lowercase. Never reused by another account.
    public_code = Column(String, nullable=True, unique=True)
    # When public_code last changed; regenerate_cooldown_remaining
    # (app/public_profile.py) allows one regeneration per 24 hours.
    public_code_regenerated_at = Column(DateTime(timezone=True), nullable=True)

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
    shared_content = relationship("SharedContent", back_populates="game_account", cascade="all, delete-orphan")
    # Friend requests/friendships this character sent and received (see
    # Friendship). Deleted with the character.
    friendships_sent = relationship(
        "Friendship", foreign_keys="Friendship.requester_id", back_populates="requester", cascade="all, delete-orphan"
    )
    friendships_received = relationship(
        "Friendship", foreign_keys="Friendship.addressee_id", back_populates="addressee", cascade="all, delete-orphan"
    )


class LinkCode(Base):
    """Short-lived, single-use code for the plugin's settings. Hash only."""

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
    """Long-lived plugin credential from exchanging a LinkCode once. Hash only;
    revocable independently.
    """

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
    """Single-use token emailed for POST /api/auth/forgot-password. Hash only;
    longer lifetime than LinkCode.
    """

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
    """Single-use token emailed to confirm the signup address. Hash only."""

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
    """Current bank contents from the plugin (POST /api/players/me/bank). A full
    snapshot: each sync deletes and replaces the player's rows, as in every
    item-source table below.
    
    item_id is OSRS's item id, not a foreign key. item_name covers
    untradeables, which have no wiki mapping, so Purchase Goals can match them
    by name (_take_owned, app/purchase_goals.py).
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
    """Current 28-slot inventory. Quantities are summed by item id on the plugin
    side.
    """

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
    """Worn equipment, one row per filled slot."""

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
    """Potion Storage contents. Not an ItemContainer; the plugin decomposes doses
    into item ids (MyscapePlugin#readPotionStorageItems).
    """

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
    """Rune Pouch contents (read from varbits). A separate table and endpoint so
    a stocked pouch cannot push an inventory sync over MAX_INVENTORY_ITEMS.
    """

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
    """PoH Seed Vault contents."""

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
    """Looting Bag contents. Single-container sources only report contents once
    opened in the current session.
    """

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
    """Tackle Box contents."""

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
    """Costume Room contents. One table, not one per furniture piece: every piece
    fires ItemContainerChanged on the same runtime-assigned container id
    (33405) with identical contents.
    """

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
    """Forestry Kit contents (portable item)."""

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
    """Master Scroll Book contents (portable item). No confirmed RuneLite
    container id exists yet, so nothing syncs here until the plugin finds one.
    """

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
    """Seed Box contents (portable item; distinct from the PoH Seed Vault)."""

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
    """Huntsman's Kit contents (portable item)."""

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
    """Cargo hold of one of up to five boats; `slot` (1-5) picks the boat. Each
    sync replaces only rows matching (game_account_id, slot).
    """

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
    """A named equipment+inventory loadout (Purchase Goals). Pricing and
    ownership are computed on read (app/purchase_goals.py). `equipment` (slot
    name -> item; GEAR_SETUP_EQUIPMENT_SLOTS in app/schemas.py) and
    `inventory` (28 entries) are JSON blobs because slot contents are
    polymorphic.
    
    IMPORTANT: SQLAlchemy only detects JSONB changes when a new object is
    assigned (setup.equipment = {...}), not on in-place mutation, so writes in
    app/main.py assign a whole new dict/list.
    """

    __tablename__ = "gear_setups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    icon = Column(JSONB, nullable=True)
    equipment = Column(JSONB, nullable=False, default=dict)
    inventory = Column(JSONB, nullable=False, default=lambda: [None] * 28)
    # low_to_high, high_to_low, alphabetical, reverse_alphabetical or custom
    # (_still_to_purchase_summary, app/purchase_goals.py).
    still_to_purchase_sort_mode = Column(String, nullable=False, default="low_to_high")
    # Drag order for "custom": [{"slotType": "equipment"|"inventory", "slot":
    # <str|int>}]. Unlisted items fall back to cost-ascending.
    still_to_purchase_custom_order = Column(JSONB, nullable=True)
    # Drag order of the setup list; build_gear_setups orders by this, then
    # created_at. Reorders rewrite all rows to positions 0, 1, 2, ...
    sort_order = Column(Float, nullable=True)

    game_account = relationship("GameAccount", back_populates="gear_setups")


class MindMap(Base):
    """A player-created goal/idea tree (Mindmaps). `nodes` is one JSONB blob
    because a mindmap is read and written whole: a flat list of {"id",
    "parentId", "text", "color", "order"} (parentId None for the single root).
    Tree logic: app/mindmaps.py.
    """

    __tablename__ = "mindmaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    nodes = Column(JSONB, nullable=False, default=list)

    game_account = relationship("GameAccount", back_populates="mindmaps")


class Goal(Base):
    """Goal Tracking goals, one row per target (boss kills, skill level/xp or
    item quantity); progress is computed live in app/goals.py.
    
    goal_type is "kc", "skill" or "item" (app.goals.GOAL_TYPES). target_name
    is the HISCORE_BOSSES name, the lowercase skill name, or a free-text item
    name. "kc" goals read GameAccount.boss_kill_counts. metric ("level"/"xp")
    is only for "skill" goals; item_id (icon only) only for "item" goals.
    
    is_recurring/recur_*: a "kc" or "skill" goal repeats per period
    (app.goals.maybe_roll_recurring_period).
    
    baseline_value is the absolute_value() reading progress is measured from
    (current_value() reports the change since). Set for recurring goals and
    one-time GAIN-mode goals; null for REACH-mode and "item" goals.
    """

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
    # Drag order for "custom" goal sort mode; nullable, rewritten to plain
    # positions on reorder. The client re-sorts locally and falls back to
    # created_at for NULLs.
    sort_order = Column(Float, nullable=True)

    game_account = relationship("GameAccount", back_populates="goals")


class LootEvent(Base):
    """One kill/casket/pickpocket's loot (POST /api/players/me/loot; see
    app/loot.py). A historical log, so syncs insert; event_id (random id from
    the plugin) makes retries idempotent.
    
    RuneLite reports every clue casket as the bare "Casket"; the plugin
    relabels it "Clue Scroll (<Tier>)" when it can pair it with the
    trail-completion chat line, so older or unpaired events stay "Casket".
    """

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
    """A Possessions Monitoring tracker (app/possessions.py). `kind` is a MINIMUM
    tracker (want at least target_quantity) or a MAXIMUM tracker (flag above
    it). item_name is a display fallback when icon/name lookup fails. Current
    quantity is computed live (get_owned_quantity_map). sort_order is a float
    so rows can be inserted between others.
    """

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
    """An item pinned to the top of Possessions Monitoring's section 3 list.
    Merged potion-dose rows normally use the stable "(1)-dose" id
    (_resolve_dose1_display); if that lookup fails the id drifts and the pin
    stops matching.
    """

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
    """An NPC or item hidden from Loot Tracker (build_loot_state, app/loot.py);
    kind is "npc" or "item". `key` is case-insensitive: lowercased sourceName,
    "id:<itemId>" or "name:<lowercased itemName>". loot_hide_key computes it
    for both writes and reads.
    """

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
    """A storage source switched off in Possessions Monitoring's settings. Row
    present means hidden from section 3 and tracker counts; no row means
    shown. storage_key is a raw POSSESSION_STORAGE_KEYS entry
    (app/schemas.py).
    """

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
    """A saved filter+sort configuration for Storages Viewer's raw list. `config`
    is an opaque JSON blob {"sortKey", "sortDir", "filters"} owned by
    render_possessions' script; sort_order is rewritten to integer positions
    on reorder.
    """

    __tablename__ = "possession_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    config = Column(JSONB, nullable=False, default=dict)
    sort_order = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    game_account = relationship("GameAccount", back_populates="possession_views")


class SharedContent(Base):
    """A frozen snapshot of a player's data shared at myscape.io/s/<code>
    (currently Loot Tracker). Unlike GameAccount.public_code these are many
    per account and never live: `payload` is stored verbatim. content_type
    selects the renderer (app/pages/).
    
    code comes from generate_share_code (app/sharing.py). expires_at is always
    set; is_valid is a lazy read-time check and expired rows are kept.
    """

    __tablename__ = "shared_content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_account_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    code = Column(String, nullable=False, unique=True)
    content_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    game_account = relationship("GameAccount", back_populates="shared_content")

    @property
    def is_valid(self) -> bool:
        return _utcnow() < _as_aware_utc(self.expires_at)


class PermanentExample(Base):
    """A frozen copy of an example link the README points at, which keeps
    resolving after the original is deleted, expires or goes private. No
    foreign key to game_accounts, so no cascade reaches it.
    capture_permanent_examples (app/permanent_examples.py) copies it at
    startup.
    """

    __tablename__ = "permanent_examples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String, nullable=False, unique=True)
    kind = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    owner_name = Column(String, nullable=True)
    payload = Column(JSONB, nullable=False)
    model_glb = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Friendship(Base):
    """A friend request ("pending") or friendship ("accepted") between two
    GameAccounts; per character because the Character Overview privacy setting
    is. Once accepted, both see each other's private Character Overview
    (find_viewable_game_account, app/public_profile.py). At most one row per
    pair: a request meeting a pending opposite one accepts it
    (send_friend_request).
    """

    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id", name="uq_friendships_pair"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    addressee_id = Column(UUID(as_uuid=True), ForeignKey("game_accounts.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", server_default="pending")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    responded_at = Column(DateTime(timezone=True), nullable=True)

    requester = relationship("GameAccount", foreign_keys=[requester_id], back_populates="friendships_sent")
    addressee = relationship("GameAccount", foreign_keys=[addressee_id], back_populates="friendships_received")


class IconCacheEntry(Base):
    """One wiki-sourced icon image (NPC/event portraits and a few rare item
    icons), fetched once and kept until app/icon_cache.py is told to refresh
    (REFRESH_ICONS_FETCHED_BEFORE). Keyed by the /icon-cache/<filename> name,
    so it needs no id. Kept in Postgres because the Render service has no
    persistent disk (render.yaml).
    """

    __tablename__ = "icon_cache_entries"

    filename = Column(String, primary_key=True)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
