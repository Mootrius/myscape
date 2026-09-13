"""Pydantic request/response shapes for the API."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator

# The 11 equipment slots a gear setup can fill -- matches EQUIPMENT_SLOTS
# in the original Maintrius tool's osrs_tracker.py exactly (RuneLite's
# own ARMS/HAIR/JAW slots are cosmetic-only and never used in vanilla
# OSRS, so they were never part of that list either -- see
# MyscapePlugin's EQUIPMENT_SLOT_NAMES in the Mootrius/myscape-plugin
# repo for where this list is mirrored on the plugin side).
EQUIPMENT_SLOTS = [
    "head", "cape", "neck", "ammo", "weapon", "body",
    "shield", "legs", "hands", "boots", "ring",
]
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


# -- Item search (backs the gear-setup slot picker's search box). ---------

class ItemSearchResult(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None


class ItemSearchResponse(BaseModel):
    results: List[ItemSearchResult]


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
    See _resolve_gear_slot_item's docstring in the original Maintrius
    tool's osrs_tracker.py for the full rationale behind these four
    shapes -- ported here as validation on the way in:

    - Plain tradeable: item_id set, no components, not supplies.
    - Plain untradeable: item_id None, item_name set, no components.
    - Composed ("combo"): item_id None, components is a non-empty list
      -- costs the sum of its components rather than having its own
      price.
    - Supplies: supplies=True on any of the above (never combined with
      components) -- always assumed owned, never counted toward cost.
    """

    item_id: Optional[int] = None
    item_name: Optional[str] = None
    components: Optional[List[GearComponentIn]] = None
    supplies: bool = False

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

    @field_validator("supplies")
    @classmethod
    def check_supplies(cls, value, info):
        if value and info.data.get("components"):
            raise ValueError("a supplies item cannot also be a composed item.")
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
