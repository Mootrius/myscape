"""Pydantic request/response shapes for the API."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

from app.mindmaps import DIARY_AREAS, DIARY_TIERS, SKILL_NAMES

# The 11 real, in-game equipment slots -- matches EQUIPMENT_SLOTS in the
# original Maintrius tool's osrs_tracker.py exactly (RuneLite's own
# ARMS/HAIR/JAW slots are cosmetic-only and never used in vanilla OSRS,
# so they were never part of that list either -- see MyscapePlugin's
# EQUIPMENT_SLOT_NAMES in the Mootrius/myscape-plugin repo for where
# this list is mirrored on the plugin side). This is specifically the
# set of slots the RuneLite plugin can ever report worn equipment in
# (see EquipmentItemIn.check_slot and MAX_EQUIPMENT_ITEMS below) -- for
# a gear SETUP's own slots (which also include the 8 misc slots below),
# use GEAR_SETUP_EQUIPMENT_SLOTS instead.
EQUIPMENT_SLOTS = [
    "head", "cape", "neck", "ammo", "weapon", "body",
    "shield", "legs", "hands", "boots", "ring",
]
# Eight extra, purely app-side planning slots on the equipment doll --
# not real OSRS equipment slots (the RuneLite plugin never reports
# worn equipment in these, so they're excluded from EQUIPMENT_SLOTS
# above), for whatever a player wants to plan around buying alongside a
# setup's real gear: runes for a rune pouch, teleports for the setup's
# activity, and so on. Rendered as two rows of 4 below the paperdoll
# (see .gear-doll-misc in purchase-goals.css). Ownership still resolves
# the same generic way as every other slot (see _build_owned_pools in
# app/purchase_goals.py -- it's just a bank/inventory/equipment/potion-
# storage total by item, with no per-slot special-casing), so any item
# works here.
MISC_EQUIPMENT_SLOTS = ["misc1", "misc2", "misc3", "misc4", "misc5", "misc6", "misc7", "misc8"]
# All slots a gear setup's equipment dict can use -- the 11 real slots
# plus the 8 misc ones above. Used for validating/iterating a SETUP's
# own slots (set_gear_slot, move_gear_slot_item, build_gear_setups);
# EQUIPMENT_SLOTS alone remains what the real RuneLite equipment sync
# is validated against.
GEAR_SETUP_EQUIPMENT_SLOTS = EQUIPMENT_SLOTS + MISC_EQUIPMENT_SLOTS
INVENTORY_SIZE = 28


class PlayerOut(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None
    runescape_name: Optional[str] = None
    account_hash: Optional[str] = None

    class Config:
        from_attributes = True


class SignupRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) < 3:
            raise ValueError("That doesn't look like a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class VerifyEmailRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class ChangeEmailRequest(BaseModel):
    new_email: str
    current_password: str

    @field_validator("new_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) < 3:
            raise ValueError("That doesn't look like a valid email address.")
        return value


class DeleteAccountRequest(BaseModel):
    current_password: str


class PublicProfileUpdateRequest(BaseModel):
    """Body for POST /api/players/me/public-profile -- see
    GameAccount.is_public_profile's own comment in app/models.py."""
    is_public: bool


class ModelViewerBackgroundUpdateRequest(BaseModel):
    """Body for POST /api/players/me/model-viewer-background -- see
    GameAccount.model_viewer_background_index's own comment in app/
    models.py. Only a non-negative check here; the real upper bound
    (how many backgrounds actually exist) lives in
    _MODEL_VIEWER_BACKGROUNDS in app/pages.py, which that endpoint
    checks against directly rather than this schema importing from
    pages.py just for one bound, same as e.g. sync_boat_cargo's own
    slot-range check in app/main.py isn't a schema validator either."""
    index: int

    @field_validator("index")
    @classmethod
    def check_index(cls, value: int) -> int:
        if value < 0:
            raise ValueError("index must not be negative.")
        return value


class LinkStartResponse(BaseModel):
    code: str
    expires_at: datetime


class LinkExchangeRequest(BaseModel):
    code: str
    account_hash: str
    runescape_name: Optional[str] = None


class LinkExchangeResponse(BaseModel):
    api_key: str
    player_id: uuid.UUID


class GameAccountSummary(BaseModel):
    """One row in the account page's Linked Accounts list -- see
    app/routers/linking.py's game-account endpoints (step 7 of
    docs/multi-account-scoping.md). Deliberately leaves out
    account_hash: nothing on the website itself needs the raw hash,
    only whether a slot is linked at all."""

    id: uuid.UUID
    runescape_name: Optional[str] = None
    linked: bool
    active: bool


class SharedLinkSummary(BaseModel):
    """One row of the account page's Shared Links section -- GET
    /api/account/shared-links, one per currently-valid SharedContent
    row across every one of the signed-in Account's own GameAccounts
    (see app/routers/account.py). character_name is whichever
    GameAccount the link was created under, not necessarily the
    account's currently-active one -- Optional only because
    GameAccount.runescape_name itself is (an unlinked slot has none;
    not a state any share could realistically be created from, but
    the type follows the source field rather than asserting that can
    never happen). Deleting that GameAccount entirely takes its
    SharedContent rows with it (see the cascade on GameAccount.
    shared_content in app/models.py), so this never needs to represent
    "character since deleted" -- the row is simply gone too.
    content_type_label is the
    human-readable app name (SHARE_CONTENT_TYPE_LABELS in
    app/sharing.py) -- content_type itself stays the raw internal
    string, not shown anywhere, kept here mainly so a future
    content-type-specific action (if one's ever needed) has something
    to key off without another round trip. expires_at is a plain
    datetime -- the frontend formats it for display itself, same as
    every other timestamp this app's JSON already hands over raw."""

    id: uuid.UUID
    code: str
    # Full https://myscape.io/s/<code> link -- built server-side (see
    # list_shared_links in app/routers/account.py) from the same
    # _SITE_URL constant every other share/public-profile link already
    # uses, rather than having the frontend reassemble it from `code`
    # alone -- one less place that would need updating if the URL
    # scheme ever changed.
    url: str
    content_type: str
    content_type_label: str
    character_name: Optional[str] = None
    expires_at: datetime


class BankItemIn(BaseModel):
    item_id: int
    # Only meaningfully used for an untradeable item (see BankItem's
    # docstring in app/models.py) -- sent for every item regardless,
    # since the plugin has no cheap way to know ahead of time which
    # items are tradeable and which aren't.
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class BankSyncRequest(BaseModel):
    items: List[BankItemIn]


class BankSyncResponse(BaseModel):
    item_count: int


class BankItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class BankOut(BaseModel):
    items: List[BankItemOut]
    updated_at: Optional[datetime] = None


# -- Inventory: identical shape to Bank above, just a separate container. --

class InventoryItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class InventorySyncRequest(BaseModel):
    items: List[InventoryItemIn]


class InventorySyncResponse(BaseModel):
    item_count: int


class InventoryItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class InventoryOut(BaseModel):
    items: List[InventoryItemOut]
    updated_at: Optional[datetime] = None


# -- Equipment: keyed by slot rather than a flat list. --------------------

class EquipmentItemIn(BaseModel):
    slot: str
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("slot")
    @classmethod
    def check_slot(cls, value: str) -> str:
        if value not in EQUIPMENT_SLOTS:
            raise ValueError(f"slot must be one of {EQUIPMENT_SLOTS}")
        return value

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class EquipmentSyncRequest(BaseModel):
    items: List[EquipmentItemIn]

    @field_validator("items")
    @classmethod
    def check_unique_slots(cls, value: List[EquipmentItemIn]) -> List[EquipmentItemIn]:
        slots = [item.slot for item in value]
        if len(slots) != len(set(slots)):
            raise ValueError("each equipment slot can only appear once per sync.")
        return value


class EquipmentSyncResponse(BaseModel):
    item_count: int


class EquipmentItemOut(BaseModel):
    slot: str
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class EquipmentOut(BaseModel):
    items: List[EquipmentItemOut]
    updated_at: Optional[datetime] = None


# -- Potion storage: identical shape to Bank/Inventory above, just a
# separate container -- see PotionStorageItem's docstring in
# app/models.py for why this exists. ---------------------------------

class PotionStorageItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class PotionStorageSyncRequest(BaseModel):
    items: List[PotionStorageItemIn]


class PotionStorageSyncResponse(BaseModel):
    item_count: int


class PotionStorageItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class PotionStorageOut(BaseModel):
    items: List[PotionStorageItemOut]
    updated_at: Optional[datetime] = None


# -- Rune pouch: identical shape to Bank/Inventory/Potion Storage above,
# just a separate container -- see RunePouchItem's docstring in
# app/models.py for why this exists. ----------------------------------

class RunePouchItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class RunePouchSyncRequest(BaseModel):
    items: List[RunePouchItemIn]


class RunePouchSyncResponse(BaseModel):
    item_count: int


class RunePouchItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class RunePouchOut(BaseModel):
    items: List[RunePouchItemOut]
    updated_at: Optional[datetime] = None


# -- Seed vault: identical shape to Rune Pouch above, just a separate
# container -- see SeedVaultItem's docstring in app/models.py. --------

class SeedVaultItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class SeedVaultSyncRequest(BaseModel):
    items: List[SeedVaultItemIn]


class SeedVaultSyncResponse(BaseModel):
    item_count: int


class SeedVaultItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class SeedVaultOut(BaseModel):
    items: List[SeedVaultItemOut]
    updated_at: Optional[datetime] = None


# -- Looting bag: identical shape to Bank/Rune Pouch/Seed Vault above,
# just a separate container -- see LootingBagItem's docstring in
# app/models.py. -------------------------------------------------------

class LootingBagItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class LootingBagSyncRequest(BaseModel):
    items: List[LootingBagItemIn]


class LootingBagSyncResponse(BaseModel):
    item_count: int


class LootingBagItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class LootingBagOut(BaseModel):
    items: List[LootingBagItemOut]
    updated_at: Optional[datetime] = None


# -- Tackle Box: identical shape to Looting Bag/Seed Vault above, just
# a separate container -- see TackleBoxItem's docstring in
# app/models.py. -----------------------------------------------------

class TackleBoxItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class TackleBoxSyncRequest(BaseModel):
    items: List[TackleBoxItemIn]


class TackleBoxSyncResponse(BaseModel):
    item_count: int


class TackleBoxItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class TackleBoxOut(BaseModel):
    items: List[TackleBoxItemOut]
    updated_at: Optional[datetime] = None

# -- PoH: identical shape to Looting Bag/Seed Vault above, just a
# separate container -- see PohItem's docstring in app/models.py for
# why this is one unified schema (and named "PoH" rather than "Costume
# Room") rather than six per-piece ones. --------------------------------

class PohItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class PohSyncRequest(BaseModel):
    items: List[PohItemIn]


class PohSyncResponse(BaseModel):
    item_count: int


class PohItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class PohOut(BaseModel):
    items: List[PohItemOut]
    updated_at: Optional[datetime] = None


# -- Forestry Kit: identical shape to Looting Bag/Seed Vault above,
# just a separate container -- see ForestryKitItem's docstring in
# app/models.py. --------------------------------------------------------

class ForestryKitItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class ForestryKitSyncRequest(BaseModel):
    items: List[ForestryKitItemIn]


class ForestryKitSyncResponse(BaseModel):
    item_count: int


class ForestryKitItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class ForestryKitOut(BaseModel):
    items: List[ForestryKitItemOut]
    updated_at: Optional[datetime] = None


# -- Master Scroll Book: identical shape to Looting Bag/Seed Vault
# above, just a separate container -- see MasterScrollBookItem's
# docstring in app/models.py for why this may not actually receive
# real syncs yet. --------------------------------------------------------

class MasterScrollBookItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class MasterScrollBookSyncRequest(BaseModel):
    items: List[MasterScrollBookItemIn]


class MasterScrollBookSyncResponse(BaseModel):
    item_count: int


class MasterScrollBookItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class MasterScrollBookOut(BaseModel):
    items: List[MasterScrollBookItemOut]
    updated_at: Optional[datetime] = None


# -- Seed Box: identical shape to Looting Bag/Seed Vault above, just a
# separate container -- see SeedBoxItem's docstring in app/models.py.
# Distinct from SeedVaultOut above (the PoH Seed Vault). -----------------

class SeedBoxItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class SeedBoxSyncRequest(BaseModel):
    items: List[SeedBoxItemIn]


class SeedBoxSyncResponse(BaseModel):
    item_count: int


class SeedBoxItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class SeedBoxOut(BaseModel):
    items: List[SeedBoxItemOut]
    updated_at: Optional[datetime] = None


# -- Huntsman's Kit: identical shape to Tackle Box/Forestry Kit above,
# just a separate container -- see HuntsmansKitItem's docstring in
# app/models.py. Grouped under "PORTABLE" on Storages Viewer, same as
# those two. -------------------------------------------------------------

class HuntsmansKitItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class HuntsmansKitSyncRequest(BaseModel):
    items: List[HuntsmansKitItemIn]


class HuntsmansKitSyncResponse(BaseModel):
    item_count: int


class HuntsmansKitItemOut(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class HuntsmansKitOut(BaseModel):
    items: List[HuntsmansKitItemOut]
    updated_at: Optional[datetime] = None


# -- Boat Cargo: its own new "BOATS" section on Storages Viewer, right
# after PoH -- see BoatCargoItem's docstring in app/models.py for why
# this one carries a `slot` (1-5, one of a player's up to five
# independently-owned boats -- see the Sailing skill's own boat-
# ownership rules) that every other storage schema here doesn't need.
# Synced and read one slot at a time (POST/GET .../boat-cargo/{slot})
# rather than all five in one request/response, specifically so a sync
# of the one boat a player is currently near never has to say anything
# -- and therefore never risks accidentally wiping anything -- about
# the other four boats' own last-known cargo. ---------------------------

class BoatCargoItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class BoatCargoSyncRequest(BaseModel):
    items: List[BoatCargoItemIn]


class BoatCargoSyncResponse(BaseModel):
    item_count: int


class BoatCargoItemOut(BaseModel):
    # Present here (unlike every other *ItemOut above) even though
    # nothing on the website currently displays it -- see
    # BoatCargoItem's own docstring in app/models.py for why the
    # underlying row always has one; dropping it on the way back out
    # would throw away real data for no reason.
    slot: int
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class BoatCargoOut(BaseModel):
    items: List[BoatCargoItemOut]
    updated_at: Optional[datetime] = None


# -- Storages Viewer: the min/max item trackers (sections 1/2)
# and the storage sync-status map the plugin side panel's Status
# section reads -- see PossessionTracker/GameAccount.storage_synced_at's
# own docstrings in app/models.py. ---------------------------------

#: Every storage source Storages Viewer (and the plugin panel's
#: Status section) knows about, in the fixed order they're always shown.
#: Kept here, not just in app/possessions.py, since main.py's sync
#: endpoints need the same key spelling to stamp storage_synced_at with.
POSSESSION_STORAGE_KEYS = [
    "bank", "equipment", "inventory", "potion_storage",
    "rune_pouch", "seed_vault", "looting_bag", "tackle_box",
    "poh", "forestry_kit", "master_scroll_book", "seed_box",
    "huntsmans_kit", "boat_cargo",
]


class SyncStatusOut(BaseModel):
    """One entry per POSSESSION_STORAGE_KEYS -- {"bank": "<iso ts>"|None,
    ...}. Read by the plugin's side panel Status section (GET
    /api/players/me/sync-status) -- session-auth isn't usable from the
    plugin (it's API-key authenticated like every other plugin-facing
    endpoint), so this is deliberately a plain dict rather than the
    website's own session-authenticated GETs above."""
    storages: Dict[str, Optional[datetime]]


class PossessionShareCreateRequest(BaseModel):
    """Body for POST /api/possessions/share -- the one piece of
    Storages Viewer's frozen snapshot that isn't already sitting in a
    persisted table at share time: which location filter GROUPS the
    sharer currently had toggled on (state.locations client-side, see
    _possessions_panel_markup's own script in app/pages.py) -- purely
    transient and resets to all-on on every real page load, unlike
    enabledStorages (HiddenPossessionStorage, already persisted and
    read straight off the account by build_possessions_share_snapshot
    without needing it here). locations is the raw per-storage key
    list (POSSESSION_STORAGE_KEYS above, not the group labels
    _POSSESSION_LOCATION_GROUPS shows on screen) -- whatever keys
    state.locations currently has flagged on, verbatim; an unknown key
    is simply dropped by build_possessions_share_snapshot rather than
    erroring, same permissive posture LootShareCreateRequest above
    takes with its own range/start/end."""

    locations: List[str] = []


class PossessionTrackerIn(BaseModel):
    kind: str  # "min" or "max"
    item_id: int
    item_name: Optional[str] = None
    target_quantity: int

    @field_validator("kind")
    @classmethod
    def check_kind(cls, value: str) -> str:
        if value not in ("min", "max"):
            raise ValueError('kind must be "min" or "max".')
        return value

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("target_quantity")
    @classmethod
    def check_target_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("target_quantity must be a positive integer.")
        return value


class PossessionTrackerUpdate(BaseModel):
    """PATCH body -- only target_quantity is ever editable after
    creation (see the page's own edit-in-place UI); swapping an
    existing tracker's item is just delete-and-recreate instead."""
    target_quantity: int

    @field_validator("target_quantity")
    @classmethod
    def check_target_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("target_quantity must be a positive integer.")
        return value


class PossessionTrackerOut(BaseModel):
    id: str
    kind: str
    item_id: int
    item_name: Optional[str] = None
    target_quantity: int
    icon: Optional[str] = None
    tradeable: bool = False
    owned_quantity: int = 0


class PossessionViewSaveRequest(BaseModel):
    """POST body for saving the current Storages Viewer filter/sort
    setup as a new named view (see render_possessions' own saved-views
    strip in app/pages.py) -- config is an opaque blob the page's own
    script builds and reads back, never validated field-by-field here
    (see PossessionView's own docstring in app/models.py for why)."""
    name: str
    config: dict

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class PossessionViewUpdateRequest(BaseModel):
    """PATCH body for an existing saved view -- rename it, replace its
    stored config with the page's current filter/sort setup, or both
    at once. At least one of the two must be present; a request with
    neither is rejected rather than silently doing nothing."""
    name: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @model_validator(mode="after")
    def check_something_present(self):
        if self.name is None and self.config is None:
            raise ValueError("Provide a name, a config, or both.")
        return self


class SetPossessionViewOrderRequest(BaseModel):
    """The full new order of a player's saved Storages Viewer views
    after a drag-and-drop reorder -- always the complete list of view
    ids as currently displayed, not a delta, same full-replacement
    convention SetGearSetupOrderRequest above follows. See sort_order
    on PossessionView in app/models.py."""
    order: List[str]


# -- Skills/quests/diaries: unlike every item source above, each of
# these is always exactly one whole snapshot (one level+xp per skill,
# one completed-quest list, one highest tier per diary area) rather
# than many independent rows -- see GameAccount.skills/completed_quests/
# diary_tiers' own comments in app/models.py. Each sync is still a full
# replace, same spirit as every item source. ---------------------------

class SkillIn(BaseModel):
    skill: str
    level: int
    xp: int

    @field_validator("skill")
    @classmethod
    def check_skill(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in SKILL_NAMES:
            raise ValueError(f"skill must be one of {sorted(SKILL_NAMES)}")
        return normalized

    @field_validator("level")
    @classmethod
    def check_level(cls, value: int) -> int:
        if not (1 <= value <= 99):
            raise ValueError("level must be between 1 and 99.")
        return value

    @field_validator("xp")
    @classmethod
    def check_xp(cls, value: int) -> int:
        if value < 0:
            raise ValueError("xp can't be negative.")
        return value


class SkillsSyncRequest(BaseModel):
    skills: List[SkillIn]


class SkillsSyncResponse(BaseModel):
    skill_count: int


class QuestsSyncRequest(BaseModel):
    completed_quests: List[str]
    # New alongside completed_quests, not replacing it -- see
    # GameAccount.in_progress_quests' own comment in app/models.py.
    # Defaulted to [] rather than required, so an older plugin build
    # that only ever sends completed_quests doesn't fail this sync
    # outright -- sync_quests below just treats a missing/empty list
    # the same as "nothing in progress right now".
    in_progress_quests: List[str] = []


class QuestsSyncResponse(BaseModel):
    quest_count: int


class DiaryTierIn(BaseModel):
    area: str
    tier: str

    @field_validator("area")
    @classmethod
    def check_area(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in DIARY_AREAS:
            raise ValueError(f"area must be one of {sorted(DIARY_AREAS)}")
        return normalized

    @field_validator("tier")
    @classmethod
    def check_tier(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in DIARY_TIERS:
            raise ValueError(f"tier must be one of {DIARY_TIERS}")
        return normalized


class DiariesSyncRequest(BaseModel):
    diary_tiers: List[DiaryTierIn]


class DiariesSyncResponse(BaseModel):
    area_count: int


# -- Collection log: unlike skills/quests/diaries just above, this
# isn't a small fixed-shape snapshot -- it's a per-item obtained/
# quantity map. Deliberately NOT validated item-by-item here the way
# every other synced item type above is (compare BankItemIn etc.) --
# Pydantic fails a List[Model] field's ENTIRE request the instant any
# one element's own field_validator raises, so a per-item raising
# validator here would zero out a player's whole collection log sync
# over a single bad item_id/quantity (a stale id from an outdated
# plugin build, say) with no obvious symptom besides the page simply
# never populating. sync_collection_log in app/main.py checks each
# item against get_valid_item_ids()/quantity >= 1 itself instead, and
# drops only the offending items rather than failing the whole
# request. Still a full replace on every sync, same as every other
# current-state sync in this file -- see
# GameAccount.collection_log_items' own comment in app/models.py. -----

class CollectionLogItemIn(BaseModel):
    item_id: int
    quantity: int


class CollectionLogSyncRequest(BaseModel):
    items: List[CollectionLogItemIn]


class CollectionLogSyncResponse(BaseModel):
    item_count: int


ACCOUNT_TYPE_CODES = {"MAIN", "IRONMAN", "UIM", "HCIM", "GIM", "HCGIM", "UGIM"}


class CharacterSummarySyncRequest(BaseModel):
    """The seven stats the myscape-plugin repo reads straight off the
    in-game "Character Summary" tab -- see GameAccount's own
    character_summary_* columns in app/models.py for what each field
    means and why questsCompleted/questsTotal stands in for quest
    points. Always a full replace, like every other current-state sync
    here (skills/quests/diaries above) -- there's no incremental update
    for any of these, since the plugin always reads (and sends) the
    whole panel in one pass."""

    combat_level: float
    total_level: int
    total_xp: int
    quests_completed: int
    quests_total: int
    achievements_completed: int
    achievements_total: int
    combat_tasks_completed: int
    combat_tasks_total: int
    collections_completed: int
    collections_total: int
    # New: {<tier>: <completed count>} for the six combat achievement
    # tiers, alongside (not replacing) the aggregate combat_tasks_*
    # pair above -- see GameAccount.character_summary_combat_task_tier_
    # completed's own comment in app/models.py. Defaulted to {} rather
    # than required, same backward-compatibility reasoning
    # QuestsSyncRequest.in_progress_quests above gives.
    combat_task_tier_completed: Dict[str, int] = {}
    # New: one of ACCOUNT_TYPE_CODES above -- see GameAccount.
    # account_type's own comment in app/models.py for where this comes
    # from (client.getVarbitValue(Varbits.ACCOUNT_TYPE), not the panel
    # itself) and what it replaces. Optional/defaulted to None rather
    # than required, same backward-compatibility reasoning
    # combat_task_tier_completed above gives -- an older plugin build
    # that doesn't send this yet shouldn't have every other field in
    # this same sync start failing because of it.
    account_type: Optional[str] = None

    @field_validator("combat_task_tier_completed")
    @classmethod
    def check_combat_task_tier_completed(cls, value: Dict[str, int]) -> Dict[str, int]:
        valid_tiers = {"easy", "medium", "hard", "elite", "master", "grandmaster"}
        bad = set(value) - valid_tiers
        if bad:
            raise ValueError(f"combat_task_tier_completed has unknown tier(s): {sorted(bad)}")
        return value

    @field_validator("account_type")
    @classmethod
    def check_account_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in ACCOUNT_TYPE_CODES:
            raise ValueError(f"account_type must be one of {sorted(ACCOUNT_TYPE_CODES)}, got {value!r}")
        return value


class CharacterSummarySyncResponse(BaseModel):
    stat_count: int


class CharacterModelSyncRequest(BaseModel):
    """A single .glb (glTF 2.0 binary) file, base64-encoded -- see
    GameAccount.character_model_glb's own docstring in app/models.py
    for what this actually is and why it's sent base64-in-JSON rather
    than as a raw multipart/octet-stream upload (MyscapeClient#
    syncCharacterModel in the Mootrius/myscape-plugin repo reuses this
    app's existing sync* JSON contract rather than adding a second,
    differently-shaped upload path just for this one endpoint)."""

    glb_base64: str


class CharacterModelSyncResponse(BaseModel):
    # The server's own count of bytes actually stored, once decoded --
    # not just an echo of len(request.glb_base64) -- so this also
    # doubles as a sanity check that nothing was corrupted/truncated in
    # transit, the same role syncCharacterModel's own docstring
    # describes client-side.
    byte_count: int


# -- Item search (backs the gear-setup slot picker's search box). ---------

class ItemSearchResult(BaseModel):
    # id is None for a known item-combination recipe match (e.g.
    # "Neitiznot faceguard" -- see app/recipes.py) that has no Grand
    # Exchange listing of its own to carry a real item id; tradeable is
    # False in exactly that case, so the frontend can tell the two
    # apart without guessing from id alone.
    id: Optional[int] = None
    name: str
    icon: Optional[str] = None
    tradeable: bool = True


class ItemSearchResponse(BaseModel):
    results: List[ItemSearchResult]


class NpcSearchResponse(BaseModel):
    """Backs the Mindmaps KC goal's NPC search field (see
    app/npc_names.py) -- just names, unlike item search, since there's
    no per-NPC icon snapshot to show alongside a suggestion."""

    results: List[str]


class QuestSearchResponse(BaseModel):
    """Backs the Mindmaps QUEST goal's quest/miniquest search field
    (see app/quest_names.py)."""

    results: List[str]


# -- Gear setups (Purchase Goals). -----------------------------------------

class GearSetupIconIn(BaseModel):
    """A setup's purely cosmetic icon -- itemId set for a tradeable item
    (icon looked up server-side), or None with itemName set for an
    untradeable one (the frontend builds its own icon URL from the
    name, the same trick used throughout this feature -- see
    item_icon_url in app/purchase_goals.py)."""

    item_id: Optional[int] = None
    item_name: Optional[str] = None

    @field_validator("item_name")
    @classmethod
    def require_name_for_untradeable(cls, value, info):
        item_id = info.data.get("item_id")
        if item_id is None and not (value or "").strip():
            raise ValueError("item_name is required when item_id is not set.")
        return value


class SetGearSetupIconRequest(BaseModel):
    icon: Optional[GearSetupIconIn] = None


class GearComponentIn(BaseModel):
    """One ingredient of a composed ("combo") slot item -- see
    GearSlotItemIn.components."""

    item_id: Optional[int] = None
    item_name: Optional[str] = None
    quantity: int = 1

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value < 1:
            raise ValueError("component quantity must be at least 1.")
        return value

    @field_validator("item_name")
    @classmethod
    def require_name_for_untradeable(cls, value, info):
        item_id = info.data.get("item_id")
        if item_id is None and not (value or "").strip():
            raise ValueError("component item_name is required when item_id is not set.")
        return value


class GearSlotItemIn(BaseModel):
    """What's stored in one gear-setup slot (equipment or inventory).
    See _resolve_gear_slot_item's docstring in app/purchase_goals.py
    for the full rationale behind these three shapes -- ported here as
    validation on the way in:

    - Plain tradeable: item_id set, no components.
    - Plain untradeable: item_id None, item_name set, no components.
    - Composed ("combo"): item_id None, components is a non-empty list
      -- costs the sum of its components rather than having its own
      price.

    A fourth shape, "supplies" (always assumed owned regardless of
    what was actually held, never counted toward cost), used to exist
    here as a manual escape hatch for potions -- the plugin had no way
    to see what was sitting in Potion Storage, so there was no way to
    ever recognize a stored potion as genuinely owned. Now that the
    plugin reads Potion Storage directly (see PotionStorageItem's
    docstring in app/models.py), ownership is checked for real instead,
    and that shape is gone.
    """

    item_id: Optional[int] = None
    item_name: Optional[str] = None
    components: Optional[List[GearComponentIn]] = None

    @field_validator("item_name")
    @classmethod
    def require_name_for_untradeable(cls, value, info):
        item_id = info.data.get("item_id")
        if item_id is None and not (value or "").strip():
            raise ValueError("item_name is required when item_id is not set.")
        return value

    @field_validator("components")
    @classmethod
    def check_components(cls, value, info):
        item_id = info.data.get("item_id")
        if value is not None:
            if item_id is not None:
                raise ValueError("a composed item cannot also have a tradeable item_id.")
            if len(value) == 0:
                raise ValueError("components must be a non-empty list.")
        return value


class SetGearSlotRequest(BaseModel):
    slot_type: str  # "equipment" | "inventory"
    slot: Any  # slot name (str) for equipment, index (int) for inventory
    item: Optional[GearSlotItemIn] = None

    @field_validator("slot_type")
    @classmethod
    def check_slot_type(cls, value: str) -> str:
        if value not in ("equipment", "inventory"):
            raise ValueError("slot_type must be 'equipment' or 'inventory'.")
        return value


class MoveGearSlotItemRequest(BaseModel):
    """Drag-and-drop payload: move whatever's in (from_slot_type,
    from_slot) into (to_slot_type, to_slot). If the destination already
    holds an item, the two simply swap places rather than the source's
    old item being lost -- see move_gear_slot_item in app/main.py."""

    from_slot_type: str  # "equipment" | "inventory"
    from_slot: Any  # slot name (str) for equipment, index (int) for inventory
    to_slot_type: str  # "equipment" | "inventory"
    to_slot: Any

    @field_validator("from_slot_type", "to_slot_type")
    @classmethod
    def check_slot_type(cls, value: str) -> str:
        if value not in ("equipment", "inventory"):
            raise ValueError("slot_type must be 'equipment' or 'inventory'.")
        return value


STILL_TO_PURCHASE_SORT_MODES = (
    "low_to_high", "high_to_low", "alphabetical", "reverse_alphabetical", "custom",
)


class SetStillToPurchaseSortRequest(BaseModel):
    """Switches a setup's "Still to Purchase" list between the five
    sort modes the buttons above that list offer -- see
    still_to_purchase_sort_mode on GearSetup in app/models.py."""

    sort_mode: str

    @field_validator("sort_mode")
    @classmethod
    def check_sort_mode(cls, value: str) -> str:
        if value not in STILL_TO_PURCHASE_SORT_MODES:
            raise ValueError(f"sort_mode must be one of {STILL_TO_PURCHASE_SORT_MODES}")
        return value


class StillToPurchaseOrderEntryIn(BaseModel):
    """One row of a drag-and-drop-reordered "Still to Purchase" list --
    a still-to-purchase row IS a specific equipment/inventory slot (see
    build_gear_setups in app/purchase_goals.py), so this is the same
    slot-identity shape MoveGearSlotItemRequest's from/to use."""

    slot_type: str  # "equipment" | "inventory"
    slot: Any  # slot name (str) for equipment, index (int) for inventory

    @field_validator("slot_type")
    @classmethod
    def check_slot_type(cls, value: str) -> str:
        if value not in ("equipment", "inventory"):
            raise ValueError("slot_type must be 'equipment' or 'inventory'.")
        return value


class SetStillToPurchaseOrderRequest(BaseModel):
    """The full new row order after a drag-and-drop reorder in "custom"
    sort mode -- always the complete list as currently displayed, not a
    delta, mirroring how set_gear_slot/move_gear_slot_item always store
    a full replacement rather than a patch. See
    still_to_purchase_custom_order on GearSetup in app/models.py."""

    order: List[StillToPurchaseOrderEntryIn]


class SetGearSetupOrderRequest(BaseModel):
    """The full new order of a player's gear setup LIST after a drag-
    and-drop reorder (contrast SetStillToPurchaseOrderRequest above,
    which reorders the rows INSIDE one setup) -- always the complete
    list of setup ids as currently displayed, not a delta, same
    full-replacement convention every other reorder here follows. See
    sort_order on GearSetup in app/models.py."""

    order: List[str]


class CreateGearSetupRequest(BaseModel):
    name: str = ""


class RenameGearSetupRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name is required.")
        return value


# -- Gear setups, resolved for display (priced/owned-checked). ------------
# These aren't validated request bodies -- just typed enough to document
# the shape build_gear_setups() in app/purchase_goals.py returns, which
# FastAPI serializes straight from plain dicts (response_model isn't
# used for these -- the shape is too dynamic/nested to usefully pin down
# in Pydantic, matching how loosely the original tool's own JSON API
# treated it).
class GearSetupsState(BaseModel):
    """Documents (not enforced) the payload GET /api/gear-setups returns:
    coins, gearSetups (each with equipment/inventory/stillToPurchase/
    nextPurchase), ownedItems, pricesUpdatedAt/pricesError,
    mappingError. See build_purchase_goals_state in
    app/purchase_goals.py."""

    class Config:
        extra = "allow"


# -- Loot Tracker: an append-only log of kills/caskets/pickpockets, not
# a current-state snapshot -- see LootEvent's docstring in app/models.py
# for why its sync shape (POST /api/players/me/loot) doesn't match the
# delete-and-replace pattern every other sync endpoint above uses. -----

class LootEventItemIn(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class LootEventIn(BaseModel):
    # Client-generated once, the moment the drop happens (see
    # LootEvent's docstring in app/models.py) -- what makes a retried or
    # duplicated sync of the same event safe rather than double-counted.
    event_id: str
    source_name: str
    source_type: str
    combat_level: Optional[int] = None
    occurred_at: datetime
    items: List[LootEventItemIn]

    @field_validator("event_id", "source_name", "source_type")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("must not be empty.")
        return value


class LootSyncRequest(BaseModel):
    events: List[LootEventIn]


class LootSyncResponse(BaseModel):
    # How many of the events in this request were actually new -- a
    # number smaller than len(events) is normal and not an error (some
    # were already on file; see LootEvent's docstring), not just a
    # smaller-than-expected count to be surprised by.
    added_count: int


# -- Goal Tracking's live kill-count feed: one chatbox-parsed reading at
# a time from the RuneLite plugin (POST /api/players/me/kill-counts),
# same shape family as the loot sync models just above -- see
# apply_kill_count_updates's own docstring in app/hiscores.py for the
# full picture (a hiscores pull only ever seeds a baseline on link/
# relink now; this is the live source of truth after that). ----------

class KillCountUpdateIn(BaseModel):
    # Exactly as RuneLite's own chatbox worded it (see
    # KILLCOUNT_PATTERN's own comment in MyscapePlugin.java) --
    # matched case-insensitively against app.bosses.CHAT_NAME_TO_DISPLAY_NAME
    # server-side, not normalized here.
    boss_name: str
    kill_count: int

    @field_validator("boss_name")
    @classmethod
    def check_boss_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("boss_name must not be empty.")
        return value

    @field_validator("kill_count")
    @classmethod
    def check_kill_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("kill_count must not be negative.")
        return value


class KillCountSyncRequest(BaseModel):
    updates: List[KillCountUpdateIn]


class KillCountSyncResponse(BaseModel):
    # How many of the updates in this request matched a known boss and
    # were actually applied -- fewer than len(updates) is normal and not
    # an error (see apply_kill_count_updates's own docstring), same
    # "partial success as a count" contract LootSyncResponse.added_count
    # already uses.
    applied_count: int


class HideLootNpcRequest(BaseModel):
    """POST/DELETE /api/players/me/loot/hidden-npcs -- see the eye
    button on each NPC tile in render_loot_tracker, app/pages.py. name
    is matched against a kill's own sourceName via npc_hide_key in
    app/loot.py (trimmed/lowercased), so any casing that actually
    appears in this player's loot history will match."""

    name: str

    @field_validator("name")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class HideLootItemRequest(BaseModel):
    """POST/DELETE /api/players/me/loot/hidden-items -- same idea as
    HideLootNpcRequest above, one level down. item_id/item_name are
    resolved to a single identity the same way item_hide_key in
    app/loot.py does (item_id when given, else item_name) -- at least
    one of the two must be present, same requirement _resolve_loot_items
    already effectively has for naming an item at all."""

    item_id: Optional[int] = None
    item_name: Optional[str] = None

    @model_validator(mode="after")
    def check_has_identity(self):
        item_name = (self.item_name or "").strip()
        if self.item_id is None and not item_name:
            raise ValueError("item_id or item_name is required.")
        self.item_name = item_name or None
        return self


class LootShareCreateRequest(BaseModel):
    """Body for POST /api/players/me/loot/share -- same range/start/end
    shape GET /api/players/me/loot already takes as query params (see
    read_loot in app/main.py), just as a POST body instead, since this
    one actually creates something (a new SharedContent row) rather
    than just reading. range/start/end are resolved the exact same way
    read_loot's own are -- resolve_range/parse_loot_range_bound in
    app/loot.py, including the same "custom missing either date falls
    back to the 24-hour default" and "bad date string is a 400"
    behavior -- so this schema itself stays this permissive (no
    cross-field validation here) and leaves all of that to the
    endpoint, matching read_loot's own division of labor exactly."""

    range: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


class LootState(BaseModel):
    """Documents (not enforced) the payload GET /api/players/me/loot
    returns, scoped to the requested ?range= (or ?range=custom&start=
    &end=, see read_loot in app/main.py): buckets, granularity
    ("hourly"/"daily"/"weekly"/"monthly"), rangeStart/rangeEnd,
    windowValue, windowKills, windowNpcs (per-NPC totals),
    npcBucketValues (per-NPC per-bucket value arrays, keyed by NPC
    name), windowItems (all-NPCs item totals), npcItems (per-NPC item
    totals, keyed by NPC name), pricesError/mappingError. See
    build_loot_state in app/loot.py."""

    class Config:
        extra = "allow"


# -- Mindmaps ---------------------------------------------------------


class CreateMindMapRequest(BaseModel):
    name: str = ""


class RenameMindMapRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name is required.")
        return value


class AddMindMapNodeRequest(BaseModel):
    """One new node, placed relative to an existing one -- see add_node
    in app/mindmaps.py for exactly what each relation does."""

    relative_to: str
    relation: str
    text: Optional[str] = None
    color: Optional[str] = None
    before: bool = False

    @field_validator("relation")
    @classmethod
    def check_relation(cls, value: str) -> str:
        if value not in ("parent", "child", "sibling"):
            raise ValueError("relation must be 'parent', 'child', or 'sibling'.")
        return value


class UpdateMindMapNodeRequest(BaseModel):
    text: Optional[str] = None
    color: Optional[str] = None
    # The node's own optional free-form note (see update_node/
    # _clean_note in app/mindmaps.py) -- None leaves it untouched
    # (same as text/color above), "" clears it back to no note.
    note: Optional[str] = None


class SetMindMapNodeGoalRequest(BaseModel):
    """Replaces a node's goal criteria -- see set_node_goal/clean_goal
    in app/mindmaps.py for the shape each color's goal type requires
    (validated there, not here, since which fields are even legal
    depends on the node's CURRENT color, something only the node itself
    -- not this request in isolation -- knows). Also how a gray node's
    manual "Complete" button works: {"manualComplete": true}.

    `note` rides along here too, alongside `goal`, purely so the
    node-popover's one Save button can save a trackable goal's criteria
    AND its note in one request/one undo step -- see
    set_mindmap_node_goal in app/main.py, which applies it via the same
    update_node a plain node-PATCH would. Optional and independent of
    `goal`: omitted or None leaves the note untouched."""

    goal: Dict[str, Any] = {}
    note: Optional[str] = None


class AddMindMapSharedChildRequest(BaseModel):
    """A new node placed as a shared CHILD of two or more existing
    ones -- the node canvas's shift-click multi-select -- see
    add_shared_child in app/mindmaps.py."""

    parent_ids: List[str]
    text: Optional[str] = None
    color: Optional[str] = None

    @field_validator("parent_ids")
    @classmethod
    def check_parent_ids(cls, value: List[str]) -> List[str]:
        if len(value) < 2:
            raise ValueError("parent_ids must include at least two nodes.")
        return value


class MindMapNodeIn(BaseModel):
    """One node as submitted by the client for a full-tree replace --
    see ReplaceMindMapNodesRequest/replace_nodes in app/mindmaps.py.
    The undo/redo buttons' snapshots are always a previous response
    from this same API (MM.undoStack/MM.redoStack just hold past
    copies of MM.data.nodes), not fresh player-authored data, so this
    mirrors the node shape the server itself hands back -- id/
    parentId/text/color/order, plus the optional extraParentIds a
    shared child carries -- rather than the narrower per-field shape
    AddMindMapNodeRequest et al. accept."""

    id: str
    parentId: Optional[str] = None
    text: str = ""
    color: str = ""
    order: float = 0.0
    extraParentIds: Optional[List[str]] = None
    goal: Optional[Dict[str, Any]] = None
    # A node's own optional note (see MM.undoStack/replace_nodes) --
    # missing this meant every undo/redo snapshot silently dropped it
    # before replace_nodes ever saw it (Pydantic drops any field not
    # declared on the model), even though the client's own PUT body
    # included it correctly.
    note: Optional[str] = None


class ReplaceMindMapNodesRequest(BaseModel):
    """Restores a mindmap's whole node list to a previously-seen
    snapshot -- what the undo/redo buttons use in place of a
    confirm-before-delete dialog (see replace_nodes in
    app/mindmaps.py)."""

    nodes: List[MindMapNodeIn]


class MindMapsState(BaseModel):
    """Documents (not enforced) the payload every Mindmaps endpoint
    returns: {"mindmaps": [...]}, each with id/name/createdAt/nodes --
    see build_mindmaps_state in app/mindmaps.py. Not pinned to a
    response_model for the same reason GearSetupsState above isn't."""

    class Config:
        extra = "allow"


# -- Goal Tracking's own flat goal list -- see app/goals.py for the
# validation/progress logic these wrap, and Goal's own docstring in
# app/models.py for why this is a normal table (one row per goal)
# rather than following Mindmaps' single-JSONB-blob shape. -----------

class GoalCreateRequest(BaseModel):
    goal_type: str
    target_name: str
    # Only meaningful (and required) for goal_type "skill" -- see
    # app.goals.clean_new_goal, which does the real validation; this
    # schema only shapes the request, it doesn't enforce per-type
    # rules itself.
    metric: Optional[str] = None
    target_value: int
    # Only meaningful for goal_type "item" -- the real OSRS item id the
    # player's search suggestion carried (see ItemSearchResult), passed
    # through purely so the goal list can show that item's actual icon
    # instead of the generic item-goal badge (Goal.item_id's own
    # docstring in app/models.py has the full reasoning). Never
    # required and never validated against target_name itself -- a
    # missing or mismatched value just costs the goal its real icon,
    # nothing about progress tracking depends on it.
    item_id: Optional[int] = None
    # A recurring goal ("kc"/"skill" only -- see
    # app.goals.RECURRING_GOAL_TYPES) repeats every recur_interval
    # recur_unit instead of tracking one lifetime total forever --
    # app.goals.clean_new_goal does the real validation (recur_unit one
    # of app.goals.RECUR_UNITS, recur_interval in range); this schema
    # only shapes the request. recur_interval/recur_unit are ignored
    # when is_recurring is false, same tolerance metric/item_id above
    # already get for a goal_type that doesn't use them.
    is_recurring: bool = False
    recur_interval: Optional[int] = None
    recur_unit: Optional[str] = None
    # A recurring goal's own choice of when its first period begins --
    # the wizard's NOW/CUSTOM toggle (stage 5, wizardStageStartHtml in
    # app/pages.py). None (NOW, the default -- also what a raw API call
    # that never knew to send this gets) means create_goal in
    # app/main.py falls back to _utcnow(), the only behavior that
    # existed before this field did. A CUSTOM pick sends a real
    # timestamp here instead, written straight onto Goal.recur_period_start
    # in its place -- see that column's own docstring in app/models.py
    # for what it actually drives (which absolute moment
    # maybe_roll_recurring_period, app/goals.py, phase-locks this goal's
    # period boundaries to, not "when progress starts being counted
    # from" -- there's no historical kc/xp/level series to reconstruct a
    # past baseline against, so baseline_value is always still captured
    # from the account's live numbers at creation time regardless of
    # what's picked here). Ignored when is_recurring is false, same
    # tolerance metric/item_id above already get for a goal_type that
    # doesn't use them. Pydantic parses whatever ISO-8601 string the
    # wizard's own local-time "YYYY-MM-DD HH:MM" field resolves to
    # (see recurStartIsoFromMasked in the script) straight into a
    # tz-aware datetime; this schema only shapes the request, it
    # doesn't validate that the goal type actually allows recurrence at
    # all -- app.goals.clean_new_goal does that, same as every other
    # recurring-only field here.
    recur_start_at: Optional[datetime] = None
    # A ONE-TIME goal's own GAIN/REACH choice (see
    # app.goals.GOAL_TARGET_MODES/clean_target_mode, which does the
    # real validation -- "gain" only for a one-time kc goal or a
    # one-time xp-metric skill goal, "reach" always allowed). None (the
    # default) means "reach" -- every one-time goal's only reading
    # before this field existed, and clean_target_mode's own fallback
    # when this is left out entirely. Ignored for a recurring goal --
    # it already has its own always-on period-relative baseline, see
    # GOAL_TARGET_MODES' own comment.
    target_mode: Optional[str] = None


class GoalOut(BaseModel):
    """current_value/progress_pct/target_display are never stored --
    computed fresh by app.goals.current_value/progress_pct/
    target_display every time a GoalOut is built (both on creation and
    on every list read), same "always derive it live" stance every
    other live-progress number in this app already takes. item_icon is
    the same kind of always-derived value, computed from the stored
    item_id via item_icon_url (app/purchase_goals.py) rather than
    stored itself, so an icon CDN change never needs a backfill.

    progress_pct is its own field, not just current_value/target_value
    left for the UI to divide itself, because that division is only
    actually correct for a kc/item/xp goal -- a LEVEL-metric skill
    goal's progress bar needs to read in xp under the hood (OSRS's own
    xp-per-level curve is exponential, so level 20 isn't "halfway" to
    level 40), and the UI has no xp table of its own to do that
    conversion with (see app.goals.progress_pct's own comment).
    current_value/target_value stay plain level numbers for that case
    regardless -- the goal list's own text still reads "LVL 20 / 40",
    just its bar fill no longer matches that ratio literally.

    current_value is already the RIGHT number for a recurring goal, or
    a one-time GAIN-mode goal, too -- how much has changed since
    whatever moment its own baseline_value was captured, not a lifetime
    total (see app.goals.current_value/Goal.baseline_value's own
    docstring in app/models.py) -- so the UI never needs to re-derive
    that itself to render the progress bar/text correctly;
    is_recurring/recur_interval/recur_unit are exposed purely so the
    goal list can show its own cadence tag (e.g. "EVERY 2 WEEKS") next
    to it. recur_period_start/baseline_value ARE both exposed now
    (unlike before baseline_value's own GAIN-mode use existed) purely
    for the info icon a recurring goal's cadence tag, or a one-time
    GAIN goal's plain progress text, grows (see goalInfoIconHtml in
    app/pages.py) -- a recurring goal's icon needs recur_period_start
    to say when its current period began and count down to the next
    one; a one-time GAIN goal's instead needs baseline_value (plus
    created_at, already exposed below) to say when it started tracking
    and from what number.

    sort_order is this goal's own position in the player's custom
    drag-and-drop order (see Goal.sort_order's own docstring in
    app/models.py) -- null for a goal that's never been manually
    placed, which the client's own sortGoals treats as "sorts after
    every goal that has one, by created_at among themselves"."""

    id: uuid.UUID
    goal_type: str
    target_name: str
    metric: Optional[str] = None
    target_value: int
    current_value: int
    progress_pct: float
    target_display: str
    item_icon: Optional[str] = None
    is_recurring: bool
    recur_interval: Optional[int] = None
    recur_unit: Optional[str] = None
    recur_period_start: Optional[datetime] = None
    baseline_value: Optional[int] = None
    sort_order: Optional[float] = None
    created_at: datetime


class GoalsResponse(BaseModel):
    """sort_mode is the player's own persisted #gtSortTabs choice (see
    GameAccount.goal_sort_mode in app/models.py) -- returned alongside
    the list itself so the page's first paint can select the right tab
    without a second round-trip, same reasoning
    setup.stillToPurchaseSort rides along on Purchase Goals' own
    state responses for."""

    goals: List[GoalOut]
    sort_mode: str


# Each of #gtSortTabs' own nine buttons (see app/pages.py) -- one
# "high"/"low" (or equivalent) pair per field the list can sort by
# (progress, type, name, recency), same one-label-two-arrows pattern
# STILL_TO_PURCHASE_SORT_MODES above already uses, plus "custom" at
# the end for a player's own drag-and-drop order (Goal.sort_order).
# "alphabetical"/"reverse_alphabetical"/"custom" reuse those exact
# values on purpose -- same field, same meaning, as Purchase Goals'
# own still-to-purchase sort.
GOAL_SORT_MODES = (
    "progress_desc", "progress_asc",
    "type_asc", "type_desc",
    "alphabetical", "reverse_alphabetical",
    "recent", "oldest",
    "custom",
)


class SetGoalSortModeRequest(BaseModel):
    """Switches Goal Tracking's own list between GOAL_SORT_MODES' nine
    modes -- see GameAccount.goal_sort_mode in app/models.py. Same
    shape as SetStillToPurchaseSortRequest above, just this page's own
    field/mode set."""

    sort_mode: str

    @field_validator("sort_mode")
    @classmethod
    def check_sort_mode(cls, value: str) -> str:
        if value not in GOAL_SORT_MODES:
            raise ValueError(f"sort_mode must be one of {GOAL_SORT_MODES}")
        return value


class GoalReorderRequest(BaseModel):
    """The full new order of a player's goal list after a drag-and-drop
    reorder in "custom" sort mode -- always the complete list of goal
    ids as currently displayed, not a delta, same full-replacement
    convention SetGearSetupOrderRequest above already follows for a
    gear setup LIST's own reorder. See Goal.sort_order in
    app/models.py."""

    order: List[str]
