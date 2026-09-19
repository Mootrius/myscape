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

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
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


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The player's OSRS display name, as reported by the RuneLite plugin
    # once it's linked. Mutable (players rename), so it's informational,
    # never the identity key -- that's account_hash below.
    runescape_name = Column(String, nullable=True)
    email = Column(String, nullable=True, unique=True)
    # Nullable because it's meaningless for a row that only ever gets
    # created by admin tooling; every row created through the real
    # signup endpoint always has one.
    password_hash = Column(String, nullable=True)
    # Bumped whenever the password changes via /api/auth/reset-password
    # (see that endpoint in app/routers/auth.py). The session cookie
    # set at login carries a snapshot of this value (see log_in_player
    # in app/auth.py); a session whose snapshot no longer matches the
    # player's current value is treated as stale and logged out. That's
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
    # RuneLite's stable per-account identifier. Nullable until the first
    # successful link-code exchange, unique once set so one game account
    # can't be linked to two myscape players.
    account_hash = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Three more player-state snapshots synced by the RuneLite plugin,
    # alongside bank/inventory/equipment/etc. above -- what Mindmaps'
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
    # diary_tiers: {<diary area name, lowercase>: <highest tier
    # completed, one of DIARY_TIERS in app/mindmaps.py>} -- only the
    # highest tier is kept per area (finishing Elite implies Hard/
    # Medium/Easy are done too), matching how the in-game diary journal
    # itself only ever shows one current tier per area. Synced by POST
    # /api/players/me/diaries, full replace.
    diary_tiers = Column(JSONB, nullable=False, default=dict)

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

    link_codes = relationship("LinkCode", back_populates="player", cascade="all, delete-orphan")
    api_keys = relationship("PlayerApiKey", back_populates="player", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="player", cascade="all, delete-orphan")
    email_verification_tokens = relationship("EmailVerificationToken", back_populates="player", cascade="all, delete-orphan")
    bank_items = relationship("BankItem", back_populates="player", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="player", cascade="all, delete-orphan")
    equipment_items = relationship("EquipmentItem", back_populates="player", cascade="all, delete-orphan")
    potion_storage_items = relationship("PotionStorageItem", back_populates="player", cascade="all, delete-orphan")
    rune_pouch_items = relationship("RunePouchItem", back_populates="player", cascade="all, delete-orphan")
    seed_vault_items = relationship("SeedVaultItem", back_populates="player", cascade="all, delete-orphan")
    looting_bag_items = relationship("LootingBagItem", back_populates="player", cascade="all, delete-orphan")
    tackle_box_items = relationship("TackleBoxItem", back_populates="player", cascade="all, delete-orphan")
    poh_items = relationship("PohItem", back_populates="player", cascade="all, delete-orphan")
    forestry_kit_items = relationship("ForestryKitItem", back_populates="player", cascade="all, delete-orphan")
    master_scroll_book_items = relationship("MasterScrollBookItem", back_populates="player", cascade="all, delete-orphan")
    seed_box_items = relationship("SeedBoxItem", back_populates="player", cascade="all, delete-orphan")
    huntsmans_kit_items = relationship("HuntsmansKitItem", back_populates="player", cascade="all, delete-orphan")
    boat_cargo_items = relationship("BoatCargoItem", back_populates="player", cascade="all, delete-orphan")
    gear_setups = relationship("GearSetup", back_populates="player", cascade="all, delete-orphan")
    loot_events = relationship("LootEvent", back_populates="player", cascade="all, delete-orphan")
    mindmaps = relationship("MindMap", back_populates="player", cascade="all, delete-orphan")
    possession_trackers = relationship("PossessionTracker", back_populates="player", cascade="all, delete-orphan")
    pinned_possession_items = relationship("PinnedPossessionItem", back_populates="player", cascade="all, delete-orphan")
    hidden_loot_entries = relationship("HiddenLootEntry", back_populates="player", cascade="all, delete-orphan")
    hidden_possession_storages = relationship("HiddenPossessionStorage", back_populates="player", cascade="all, delete-orphan")


class LinkCode(Base):
    """A short-lived, single-use code generated by the website for a
    signed-in player, to be pasted into the RuneLite plugin's settings.
    Only its hash is stored -- the raw code is shown to the player
    exactly once, at generation time, and never persisted or logged."""

    __tablename__ = "link_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    code_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    player = relationship("Player", back_populates="link_codes")

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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    player = relationship("Player", back_populates="api_keys")

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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    player = relationship("Player", back_populates="password_reset_tokens")

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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    player = relationship("Player", back_populates="email_verification_tokens")

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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="bank_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_bank_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="inventory_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_inventory_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    slot = Column(String, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="equipment_items")

    __table_args__ = (UniqueConstraint("player_id", "slot", name="uq_equipment_items_player_slot"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="potion_storage_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_potion_storage_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="rune_pouch_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_rune_pouch_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="seed_vault_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_seed_vault_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="looting_bag_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_looting_bag_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="tackle_box_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_tackle_box_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="poh_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_poh_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="forestry_kit_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_forestry_kit_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="master_scroll_book_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_master_scroll_book_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="seed_box_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_seed_box_items_player_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="huntsmans_kit_items")

    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_huntsmans_kit_items_player_item"),)


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
    Deleting and replacing only rows matching (player_id, slot) on each
    sync -- never every row for the player -- is what keeps a sync of
    the boat the player happens to be standing near from wiping out
    what's already known about their other boats.

    Rolled up into a single "boat_cargo" entry in
    Player.storage_synced_at and Storages Viewer's own location
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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    slot = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="boat_cargo_items")

    __table_args__ = (UniqueConstraint("player_id", "slot", "item_id", name="uq_boat_cargo_items_player_slot_item"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
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

    player = relationship("Player", back_populates="gear_setups")


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    nodes = Column(JSONB, nullable=False, default=list)

    player = relationship("Player", back_populates="mindmaps")


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
    and a sync that already has a matching (player_id, event_id) row is
    just skipped rather than double-counted, so a retried or
    double-submitted sync can never inflate a player's totals.

    source_type is RuneLite's own LootRecordType, lowercased ("npc",
    "player", "event", "pickpocket", "unknown") -- "event" covers clue
    scroll caskets and other non-NPC rewards, but RuneLite's bundled
    Loot Tracker plugin (the actual source of this data -- see
    MyscapePlugin#onLootReceived) reports every clue casket's
    source_name as the bare word "Casket", with no tier -- a known,
    real limitation of the event this reads, not a bug here, and not
    yet worked around (see app/loot.py's module docstring).

    items is a list of {"item_id": int, "item_name": str|None,
    "quantity": int} -- same shape as the other item-source tables'
    columns, just nested here as JSON per-event instead of one row per
    item, since a loot event's items are logically one unit (one kill's
    drops) rather than each contributing independently to a current-
    ownership pool the way bank/inventory items do."""

    __tablename__ = "loot_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    event_id = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    combat_level = Column(Integer, nullable=True)
    items = Column(JSONB, nullable=False, default=list)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="loot_events")

    __table_args__ = (UniqueConstraint("player_id", "event_id", name="uq_loot_events_player_event"),)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)  # "min" or "max"
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    target_quantity = Column(Integer, nullable=False)
    sort_order = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="possession_trackers")

    __table_args__ = (
        UniqueConstraint("player_id", "kind", "item_id", name="uq_possession_trackers_player_kind_item"),
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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    item_id = Column(Integer, nullable=False)
    pinned_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="pinned_possession_items")

    __table_args__ = (
        UniqueConstraint("player_id", "item_id", name="uq_pinned_possession_items_player_item"),
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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    key = Column(String, nullable=False)
    hidden_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="hidden_loot_entries")

    __table_args__ = (
        UniqueConstraint("player_id", "kind", "key", name="uq_hidden_loot_entries_player_kind_key"),
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
    app/possessions.py, BankItem and friends' own player_id-scoped
    tables, and the plugin panel's own Status section list -- never
    one of render_possessions' five grouped filter-button labels
    (BANK, CHARACTER, ...), which stay a purely client-side grouping
    of these same raw keys and know nothing about this table."""

    __tablename__ = "hidden_possession_storages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    storage_key = Column(String, nullable=False)
    hidden_at = Column(DateTime(timezone=True), default=_utcnow)

    player = relationship("Player", back_populates="hidden_possession_storages")

    __table_args__ = (
        UniqueConstraint("player_id", "storage_key", name="uq_hidden_possession_storages_player_key"),
    )
