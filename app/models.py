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

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base

LINK_CODE_LIFETIME = timedelta(minutes=10)


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
    # every one of the 23 real OSRS skills the plugin has reported at
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

    link_codes = relationship("LinkCode", back_populates="player", cascade="all, delete-orphan")
    api_keys = relationship("PlayerApiKey", back_populates="player", cascade="all, delete-orphan")
    bank_items = relationship("BankItem", back_populates="player", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="player", cascade="all, delete-orphan")
    equipment_items = relationship("EquipmentItem", back_populates="player", cascade="all, delete-orphan")
    potion_storage_items = relationship("PotionStorageItem", back_populates="player", cascade="all, delete-orphan")
    rune_pouch_items = relationship("RunePouchItem", back_populates="player", cascade="all, delete-orphan")
    seed_vault_items = relationship("SeedVaultItem", back_populates="player", cascade="all, delete-orphan")
    gear_setups = relationship("GearSetup", back_populates="player", cascade="all, delete-orphan")
    loot_events = relationship("LootEvent", back_populates="player", cascade="all, delete-orphan")
    mindmaps = relationship("MindMap", back_populates="player", cascade="all, delete-orphan")


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
    # "low_to_high"/"high_to_low"/"alphabetical" are computed fresh on
    # every read same as everything else here, but "custom" needs
    # somewhere to remember the player's own drag-and-drop ordering
    # between requests, hence still_to_purchase_custom_order below. See
    # _still_to_purchase_summary in app/purchase_goals.py for how all of
    # these are actually applied.
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
