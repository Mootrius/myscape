"""Pydantic request/response shapes for the API."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

from app.mindmaps import DIARY_AREAS, DIARY_TIERS, SKILL_NAMES

# The 11 real in-game equipment slots (the ones the RuneLite plugin can report
# worn gear in). Gear setups use GEAR_SETUP_EQUIPMENT_SLOTS instead.
EQUIPMENT_SLOTS = [
    "head", "cape", "neck", "ammo", "weapon", "body",
    "shield", "legs", "hands", "boots", "ring",
]
# Eight app-side planning slots on the equipment doll (runes, teleports, ...).
# Not real OSRS slots, so excluded from EQUIPMENT_SLOTS. Ownership resolves like
# any other slot (see _build_owned_pools in app/purchase_goals.py).
MISC_EQUIPMENT_SLOTS = ["misc1", "misc2", "misc3", "misc4", "misc5", "misc6", "misc7", "misc8"]
# All slots a gear setup's equipment dict can use: the 11 real slots plus the 8
# misc ones.
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
    """Body for POST /api/players/me/public-profile."""
    is_public: bool


class ModelViewerBackgroundUpdateRequest(BaseModel):
    """Body for POST /api/players/me/model-viewer-background. Only a non-negative
    check here; the upper bound is _MODEL_VIEWER_BACKGROUNDS in app/pages/,
    checked by the endpoint.
    """
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
    """One row in the account page's Linked Accounts list
    (app/routers/linking.py). account_hash is deliberately left out.
    """

    id: uuid.UUID
    runescape_name: Optional[str] = None
    linked: bool
    active: bool


class SharedLinkSummary(BaseModel):
    """One row of the account page's Shared Links section (GET
    /api/account/shared-links, app/routers/account.py).
    character_name is the GameAccount the link was created under, not
    necessarily the active one; Optional because GameAccount.runescape_name
    is. content_type_label is the display name (SHARE_CONTENT_TYPE_LABELS in
    app/sharing.py). expires_at is sent as a raw datetime.
    """

    id: uuid.UUID
    code: str
    # Full https://myscape.io/s/<code> link, built server-side
    # (list_shared_links in app/routers/account.py).
    url: str
    content_type: str
    content_type_label: str
    character_name: Optional[str] = None
    expires_at: datetime


class BankItemIn(BaseModel):
    item_id: int
    # Only meaningful for an untradeable item (see BankItem in app/models.py);
    # sent for every item since the plugin cannot tell which are tradeable.
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


# Inventory

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


# Equipment: keyed by slot rather than a flat list.

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


# Potion storage

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


# Rune pouch

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


# Seed vault

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


# Looting bag

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


# Tackle box

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

# PoH (one unified schema; see PohItem in app/models.py)

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


# Forestry kit

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


# Master scroll book

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


# Seed box (distinct from SeedVaultOut, the PoH seed vault)

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


# Huntsman's kit

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


# Boat cargo: carries a `slot` (1-5, one per owned boat; see BoatCargoItem in
# app/models.py). Synced and read one slot at a time so syncing one boat can
# never wipe the other four.

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
    # Returned even though no page shows it; the stored row always has one (see
    # BoatCargoItem in app/models.py).
    slot: int
    item_id: int
    item_name: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class BoatCargoOut(BaseModel):
    items: List[BoatCargoItemOut]
    updated_at: Optional[datetime] = None


# Storages Viewer: min/max item trackers and the storage sync-status map read by
# the plugin side panel.

# Every storage source, in display order. Also used by main.py's sync endpoints
# to stamp storage_synced_at.
POSSESSION_STORAGE_KEYS = [
    "bank", "equipment", "inventory", "potion_storage",
    "rune_pouch", "seed_vault", "looting_bag", "tackle_box",
    "poh", "forestry_kit", "master_scroll_book", "seed_box",
    "huntsmans_kit", "boat_cargo",
]


class SyncStatusOut(BaseModel):
    """One entry per POSSESSION_STORAGE_KEYS: {"bank": "<iso ts>"|None, ...}.
    Read by the plugin's Status section (GET /api/players/me/sync-status); the
    plugin is API-key authenticated, so this is a plain dict rather than a
    session-auth GET.
    """
    storages: Dict[str, Optional[datetime]]


class PossessionShareCreateRequest(BaseModel):
    """Body for POST /api/possessions/share. Carries only the transient part of
    the snapshot: the location filter groups currently toggled on
    (state.locations client-side). locations is the raw
    POSSESSION_STORAGE_KEYS list; unknown keys are dropped by
    build_possessions_share_snapshot rather than rejected.
    """

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
    """PATCH body; only target_quantity is editable (to change the item, delete
    and recreate).
    """
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
    """POST body for saving the current Storages Viewer filter/sort setup as a
    named view. config is an opaque blob built by the page script and not
    validated here (see PossessionView in app/models.py).
    """
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
    """PATCH body for a saved view: rename, replace config, or both. At least one
    is required.
    """
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
    """Full new order of a player's saved views after a drag-and-drop reorder
    (the complete id list, not a delta).
    """
    order: List[str]


# Skills/quests/diaries: each sync is one whole snapshot (not many independent
# rows) and a full replace.

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
    # Defaults to [] so older plugin builds that only send completed_quests
    # still sync; see GameAccount.in_progress_quests in app/models.py.
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


# Collection log: a per-item obtained/quantity map. Deliberately not validated
# item-by-item here: Pydantic fails the whole request when any list element's
# validator raises, so one stale item_id would zero out the entire sync.
# sync_collection_log in app/main.py drops only the bad items. Full replace on
# every sync.

class CollectionLogItemIn(BaseModel):
    item_id: int
    quantity: int


class CollectionLogSyncRequest(BaseModel):
    items: List[CollectionLogItemIn]


class CollectionLogSyncResponse(BaseModel):
    item_count: int


class CollectionLogItemAddRequest(BaseModel):
    item_name: str

    @field_validator("item_name")
    @classmethod
    def check_item_name(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 200:
            raise ValueError("item_name must be 1-200 characters.")
        return value


class CollectionLogItemAddResponse(BaseModel):
    # The collection log item id the name resolved to, or null when it was
    # ambiguous or unknown (nothing changed). applied_count is 1 or 0 to match.
    item_id: Optional[int] = None
    applied_count: int = 0


ACCOUNT_TYPE_CODES = {"MAIN", "IRONMAN", "UIM", "HCIM", "GIM", "HCGIM", "UGIM"}


class CharacterSummarySyncRequest(BaseModel):
    """The seven stats read from the in-game Character Summary tab (see
    GameAccount.character_summary_* in app/models.py). Always a full replace.
    """

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
    # {<tier>: <completed count>} for the six combat achievement tiers. Defaults
    # to {} for older plugin builds.
    combat_task_tier_completed: Dict[str, int] = {}
    # One of ACCOUNT_TYPE_CODES (see GameAccount.account_type in app/models.py).
    # Optional so older plugin builds keep syncing.
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
    """A .glb (glTF 2.0 binary) file, base64-encoded in JSON to reuse the
    plugin's existing sync* contract (see GameAccount.character_model_glb in
    app/models.py).
    """

    glb_base64: str


class CharacterModelSyncResponse(BaseModel):
    # Count of bytes actually stored after decoding; doubles as a
    # corruption/truncation check.
    byte_count: int


# Item search (backs the gear-setup slot picker).

class ItemSearchResult(BaseModel):
    # id is None for item-combination recipe matches (e.g. "Neitiznot
    # faceguard", app/recipes.py) with no Grand Exchange listing; tradeable is
    # False in exactly that case.
    id: Optional[int] = None
    name: str
    icon: Optional[str] = None
    tradeable: bool = True


class ItemSearchResponse(BaseModel):
    results: List[ItemSearchResult]


class NpcSearchResponse(BaseModel):
    """Backs the Mindmaps KC goal's NPC search field (app/npc_names.py). Names
    only; there is no per-NPC icon.
    """

    results: List[str]


class QuestSearchResponse(BaseModel):
    """Backs the Mindmaps QUEST goal's search field (app/quest_names.py)."""

    results: List[str]


# Gear setups (Purchase Goals)

class GearSetupIconIn(BaseModel):
    """A setup's cosmetic icon: itemId for a tradeable item, or None with
    itemName for an untradeable one (the frontend builds the icon URL from the
    name; see item_icon_url in app/purchase_goals.py).
    """

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
    """One ingredient of a composed ("combo") slot item; see
    GearSlotItemIn.components.
    """

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
    """What one gear-setup slot (equipment or inventory) holds. Rationale in
    _resolve_gear_slot_item (app/purchase_goals.py).
    - Plain tradeable: item_id set, no components.
    - Plain untradeable: item_id None, item_name set, no components.
    - Composed ("combo"): item_id None, non-empty components; costs the sum of
    its components.
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
    """Drag-and-drop payload: move the item at (from_slot_type, from_slot) to
    (to_slot_type, to_slot). A occupied destination swaps rather than loses
    its item (move_gear_slot_item in app/main.py).
    """

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
    """Switches a setup's "Still to Purchase" sort mode (see
    still_to_purchase_sort_mode on GearSetup in app/models.py).
    """

    sort_mode: str

    @field_validator("sort_mode")
    @classmethod
    def check_sort_mode(cls, value: str) -> str:
        if value not in STILL_TO_PURCHASE_SORT_MODES:
            raise ValueError(f"sort_mode must be one of {STILL_TO_PURCHASE_SORT_MODES}")
        return value


class StillToPurchaseOrderEntryIn(BaseModel):
    """One row of a reordered "Still to Purchase" list; a row is an
    equipment/inventory slot, so it uses the same slot identity as
    MoveGearSlotItemRequest.
    """

    slot_type: str  # "equipment" | "inventory"
    slot: Any  # slot name (str) for equipment, index (int) for inventory

    @field_validator("slot_type")
    @classmethod
    def check_slot_type(cls, value: str) -> str:
        if value not in ("equipment", "inventory"):
            raise ValueError("slot_type must be 'equipment' or 'inventory'.")
        return value


class SetStillToPurchaseOrderRequest(BaseModel):
    """Full new row order after a drag-and-drop in "custom" sort mode (complete
    list, not a delta). See still_to_purchase_custom_order on GearSetup.
    """

    order: List[StillToPurchaseOrderEntryIn]


class SetGearSetupOrderRequest(BaseModel):
    """Full new order of the gear setup list (complete id list, not a delta).
    Contrast SetStillToPurchaseOrderRequest, which reorders rows inside one
    setup. See sort_order on GearSetup.
    """

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


# Gear setups, resolved for display (priced/owned-checked)
# Typed only to document what build_gear_setups() in app/purchase_goals.py
# returns; FastAPI serializes the plain dicts directly (no response_model).
class GearSetupsState(BaseModel):
    """Documents (not enforced) the GET /api/gear-setups payload: coins,
    gearSetups (equipment/inventory/stillToPurchase/nextPurchase), ownedItems,
    pricesUpdatedAt/pricesError, mappingError. See build_purchase_goals_state
    in app/purchase_goals.py.
    """

    class Config:
        extra = "allow"


# Loot Tracker: an append-only event log, not a current-state snapshot, so its
# sync (POST /api/players/me/loot) does not use delete-and-replace (see
# LootEvent in app/models.py).

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
    # Client-generated when the drop happens; makes a retried or duplicated sync
    # idempotent (see LootEvent in app/models.py).
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
    # How many events were new; fewer than len(events) is normal (duplicates
    # already on file).
    added_count: int


# Goal Tracking's live kill-count feed: one chatbox-parsed reading at a time
# from the plugin (POST /api/players/me/kill-counts). See
# apply_kill_count_updates in app/hiscores.py.

class KillCountUpdateIn(BaseModel):
    # As worded in RuneLite's chatbox; matched case-insensitively against
    # app.bosses.CHAT_NAME_TO_DISPLAY_NAME server-side.
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
    # How many updates matched a known boss and were applied; fewer than
    # len(updates) is normal.
    applied_count: int


class RunescapeNameSyncRequest(BaseModel):
    """POST /api/players/me/runescape-name: the plugin reports the current
    display name. account_hash must match the API key's linked game account so
    a request cannot rename another character.
    """

    account_hash: str
    runescape_name: str

    @field_validator("runescape_name")
    @classmethod
    def check_name(cls, value: str) -> str:
        # RuneLite uses a non-breaking space where the game shows a space.
        value = (value or "").replace("\u00a0", " ").strip()
        if not value:
            raise ValueError("runescape_name must not be empty.")
        if len(value) > 12:
            raise ValueError("runescape_name must be at most 12 characters.")
        if not value.isprintable():
            raise ValueError("runescape_name contains invalid characters.")
        return value


class RunescapeNameSyncResponse(BaseModel):
    # 1 if the stored name changed, 0 if already current or the account_hash did
    # not belong to this key; never an error.
    updated: int


class HideLootNpcRequest(BaseModel):
    """POST/DELETE /api/players/me/loot/hidden-npcs. name is matched against a
    kill's sourceName via npc_hide_key (app/loot.py; trimmed, lowercased).
    """

    name: str

    @field_validator("name")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class HideLootItemRequest(BaseModel):
    """POST/DELETE /api/players/me/loot/hidden-items. Identity is item_id when
    given, else item_name (item_hide_key in app/loot.py); at least one is
    required.
    """

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
    """Body for POST /api/players/me/loot/share: the same range/start/end as GET
    /api/players/me/loot (read_loot in app/main.py). Deliberately no
    cross-field validation; the endpoint resolves them via
    resolve_range/parse_loot_range_bound (app/loot.py).
    """

    range: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


class LootState(BaseModel):
    """Documents (not enforced) the GET /api/players/me/loot payload for the
    requested range: buckets, granularity, rangeStart/rangeEnd, windowValue,
    windowKills, windowNpcs, npcBucketValues, windowItems, npcItems,
    pricesError/mappingError. See build_loot_state in app/loot.py.
    """

    class Config:
        extra = "allow"


# Mindmaps


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
    """One new node placed relative to an existing one; see add_node in
    app/mindmaps.py.
    """

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
    # Optional free-form note (see update_node/_clean_note in app/mindmaps.py).
    # None leaves it untouched; "" clears it.
    note: Optional[str] = None


class SetMindMapNodeGoalRequest(BaseModel):
    """Replaces a node's goal criteria. Validated in set_node_goal/clean_goal
    (app/mindmaps.py) because the legal fields depend on the node's current
    color. A gray node's manual "Complete" is {"manualComplete": true}.
    `note` rides along so the popover's single Save stores criteria and note
    in one request/undo step (set_mindmap_node_goal in app/main.py). Omitted
    or None leaves the note untouched.
    """

    goal: Dict[str, Any] = {}
    note: Optional[str] = None


class AddMindMapSharedChildRequest(BaseModel):
    """A new node placed as a shared child of two or more existing ones
    (shift-click multi-select); see add_shared_child in app/mindmaps.py.
    """

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
    """One node in a full-tree replace (see replace_nodes in app/mindmaps.py).
    Undo/redo snapshots are past server responses, so this mirrors the
    server's node shape (including extraParentIds) rather than the narrower
    add/update requests.
    """

    id: str
    parentId: Optional[str] = None
    text: str = ""
    color: str = ""
    order: float = 0.0
    extraParentIds: Optional[List[str]] = None
    goal: Optional[Dict[str, Any]] = None
    # The node's note. Must be declared: Pydantic drops undeclared fields, so
    # undo/redo snapshots would otherwise lose it.
    note: Optional[str] = None


class ReplaceMindMapNodesRequest(BaseModel):
    """Restores a mindmap's whole node list to a previous snapshot (undo/redo;
    see replace_nodes in app/mindmaps.py).
    """

    nodes: List[MindMapNodeIn]


class MindMapsState(BaseModel):
    """Documents (not enforced) the payload of every Mindmaps endpoint:
    {"mindmaps": [...]} with id/name/createdAt/nodes. See build_mindmaps_state
    in app/mindmaps.py.
    """

    class Config:
        extra = "allow"


# Goal Tracking's flat goal list; validation and progress logic live in
# app/goals.py. One row per goal (see Goal in app/models.py).

class GoalCreateRequest(BaseModel):
    goal_type: str
    target_name: str
    # Required only for goal_type "skill"; app.goals.clean_new_goal does the
    # real validation.
    metric: Optional[str] = None
    target_value: int
    # Only for goal_type "item": the item id from the search suggestion, used to
    # show the item's icon. Never validated; a missing or wrong value only costs
    # the icon.
    item_id: Optional[int] = None
    # Recurring goals ("kc"/"skill" only; app.goals.RECURRING_GOAL_TYPES) repeat
    # every recur_interval recur_unit. Validated in app.goals.clean_new_goal.
    # Both fields are ignored when is_recurring is false.
    is_recurring: bool = False
    recur_interval: Optional[int] = None
    recur_unit: Optional[str] = None
    # When a recurring goal's first period begins (the wizard's NOW/CUSTOM
    # toggle). None means create_goal (app/main.py) uses _utcnow(). A CUSTOM
    # value is written to Goal.recur_period_start, which phase-locks period
    # boundaries (maybe_roll_recurring_period, app/goals.py); baseline_value is
    # always captured from live numbers at creation. Ignored when is_recurring
    # is false.
    recur_start_at: Optional[datetime] = None
    # A one-time goal's GAIN/REACH choice (validated in
    # app.goals.GOAL_TARGET_MODES/clean_target_mode). None means "reach".
    # Ignored for recurring goals, which always use a period-relative baseline.
    target_mode: Optional[str] = None


class GoalOut(BaseModel):
    """current_value/progress_pct/target_display are never stored; app.goals
    derives them on every GoalOut build. item_icon is likewise derived from
    item_id via item_icon_url (app/purchase_goals.py).
    progress_pct is separate from current_value/target_value because the ratio
    is wrong for LEVEL-metric skill goals (the xp curve is exponential, so
    level 20 is not halfway to 40); the UI has no xp table.
    current_value/target_value stay level numbers there.
    current_value is already the change since baseline_value for recurring and
    one-time GAIN goals (see Goal.baseline_value in app/models.py).
    is_recurring/recur_interval/recur_unit feed the cadence tag;
    recur_period_start/baseline_value (plus created_at) feed the info icon
    (goalInfoIconHtml in app/pages/).
    sort_order is the position in the custom drag-and-drop order
    (Goal.sort_order); null sorts after all placed goals, by created_at.
    """

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
    """sort_mode is the persisted #gtSortTabs choice (GameAccount.goal_sort_mode
    in app/models.py), returned with the list so first paint selects the right
    tab.
    """

    goals: List[GoalOut]
    sort_mode: str


# The nine #gtSortTabs modes (app/pages/): a high/low pair per sortable field
# (progress, type, name, recency) plus "custom" (Goal.sort_order).
# "alphabetical"/"reverse_alphabetical"/"custom" match
# STILL_TO_PURCHASE_SORT_MODES.
GOAL_SORT_MODES = (
    "progress_desc", "progress_asc",
    "type_asc", "type_desc",
    "alphabetical", "reverse_alphabetical",
    "recent", "oldest",
    "custom",
)


class SetGoalSortModeRequest(BaseModel):
    """Switches Goal Tracking's list between GOAL_SORT_MODES (see
    GameAccount.goal_sort_mode in app/models.py).
    """

    sort_mode: str

    @field_validator("sort_mode")
    @classmethod
    def check_sort_mode(cls, value: str) -> str:
        if value not in GOAL_SORT_MODES:
            raise ValueError(f"sort_mode must be one of {GOAL_SORT_MODES}")
        return value


class GoalReorderRequest(BaseModel):
    """Full new order of the goal list after a drag-and-drop in "custom" mode
    (complete id list, not a delta). See Goal.sort_order in app/models.py.
    """

    order: List[str]
