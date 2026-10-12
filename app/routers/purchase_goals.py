"""Purchase Goals (gear setups) endpoints."""
import copy
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_verified_game_account_from_session
from app.database import get_db
from app.models import (
    GameAccount,
    GearSetup,
    SharedContent,
    _utcnow,
)
from app.pages import _SITE_URL
from app.purchase_goals import (
    build_purchase_goal_share_snapshot,
    build_purchase_goals_state,
    get_mapping,
    has_derived_price,
)
from app.recipes import expand_recipe_components
from app.routers.shared import _duplicate_name
from app.schemas import (
    GEAR_SETUP_EQUIPMENT_SLOTS,
    INVENTORY_SIZE,
    CreateGearSetupRequest,
    MoveGearSlotItemRequest,
    RenameGearSetupRequest,
    SetGearSetupIconRequest,
    SetGearSetupOrderRequest,
    SetGearSlotRequest,
    SetStillToPurchaseOrderRequest,
    SetStillToPurchaseSortRequest,
)
from app.sharing import SHARE_DEFAULT_LIFETIME, generate_share_code

router = APIRouter()


@router.get("/api/gear-setups")
def list_gear_setups(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The Purchase Goals page's polled state (build_purchase_goals_state in
    app/purchase_goals.py): every setup priced against synced storage, plus
    coins and wiki errors. No response_model (see GearSetupsState).
    """
    return build_purchase_goals_state(db, game_account)


@router.post("/api/gear-setups", status_code=status.HTTP_201_CREATED)
def create_gear_setup(
    payload: CreateGearSetupRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    name = (payload.name or "").strip() or "New Setup"
    setup = GearSetup(game_account_id=game_account.id, name=name, equipment={}, inventory=[None] * INVENTORY_SIZE)
    db.add(setup)
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.post("/api/gear-setups/{setup_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_gear_setup(
    setup_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """A full copy of one of the player's setups, landing at the END of the list
    (sort_order NULL). The response is the GET /api/gear-setups shape plus
    newSetupId.
    """
    source = _get_owned_gear_setup(db, game_account, setup_id)
    new_setup = GearSetup(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        name=_duplicate_name(source.name),
        icon=copy.deepcopy(source.icon),
        equipment=copy.deepcopy(source.equipment or {}),
        inventory=copy.deepcopy(source.inventory or [None] * INVENTORY_SIZE),
        still_to_purchase_sort_mode=source.still_to_purchase_sort_mode or "low_to_high",
        still_to_purchase_custom_order=copy.deepcopy(source.still_to_purchase_custom_order),
    )
    db.add(new_setup)
    db.commit()
    state = build_purchase_goals_state(db, game_account)
    state["newSetupId"] = str(new_setup.id)
    return state


@router.put("/api/gear-setups/order")
def set_gear_setup_order(
    payload: SetGearSetupOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a reorder of the gear setup LIST. payload.order is the complete id
    list; omitted ids keep their sort_order and unowned ids are ignored.
    """
    owned_setups = {
        str(s.id): s
        for s in db.query(GearSetup).filter(GearSetup.game_account_id == game_account.id).all()
    }
    for index, setup_id in enumerate(payload.order):
        setup = owned_setups.get(setup_id)
        if setup is not None:
            setup.sort_order = float(index)
    db.commit()
    return build_purchase_goals_state(db, game_account)


def _get_owned_gear_setup(db: Session, game_account: GameAccount, setup_id: str) -> GearSetup:
    try:
        setup_uuid = uuid.UUID(setup_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gear setup not found")
    setup = (
        db.query(GearSetup)
        .filter(GearSetup.id == setup_uuid, GearSetup.game_account_id == game_account.id)
        .first()
    )
    if setup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gear setup not found")
    return setup


@router.patch("/api/gear-setups/{setup_id}")
def rename_gear_setup(
    setup_id: str,
    payload: RenameGearSetupRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.name = payload.name
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.delete("/api/gear-setups/{setup_id}")
def delete_gear_setup(
    setup_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    db.delete(setup)
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.put("/api/gear-setups/{setup_id}/icon")
def set_gear_setup_icon(
    setup_id: str,
    payload: SetGearSetupIconRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Sets (or, with icon omitted/null, clears) the cosmetic icon next to a
    setup's total cost; never affects cost or ownership (see GearSetup in
    app/models.py).
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    if payload.icon is None:
        setup.icon = None
    else:
        setup.icon = {"itemId": payload.icon.item_id, "itemName": payload.icon.item_name or None}
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.put("/api/gear-setups/{setup_id}/slot")
def set_gear_slot(
    setup_id: str,
    payload: SetGearSlotRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Fills (or clears) one equipment or inventory slot. Stores what was sent,
    since pricing and ownership are computed on read, except that a plain
    untradeable item matching a recipe (app/recipes.py) is auto-expanded into
    a "combo" so e.g. "Neitiznot faceguard" can be selected directly.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)

    if payload.item is None:
        stored_item = None
    else:
        stored_item = {"itemId": payload.item.item_id, "itemName": payload.item.item_name or None}
        if payload.item.components:
            stored_item["components"] = [
                {"itemId": c.item_id, "itemName": c.item_name or None, "quantity": c.quantity}
                for c in payload.item.components
            ]
        if (
            payload.item.item_id is None
            and not payload.item.components
            and payload.item.item_name
            and not has_derived_price(payload.item.item_name)
        ):
            # Skipped for anything with a linked GE value in the ported RuneLite
            # table (has_derived_price in app/purchase_goals.py): it is priced
            # from that at read time, and wiki recipe data for some is wrong or
            # missing.
            mapping, _ = get_mapping()
            auto_components = expand_recipe_components(payload.item.item_name, mapping)
            if auto_components:
                stored_item["components"] = auto_components

    if payload.slot_type == "equipment":
        if payload.slot not in GEAR_SETUP_EQUIPMENT_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"slot must be one of {GEAR_SETUP_EQUIPMENT_SLOTS}"
            )
        # New dict, not an in-place mutation; see the IMPORTANT note on
        # GearSetup in app/models.py (JSONB tracking).
        equipment = dict(setup.equipment or {})
        if stored_item is None:
            equipment.pop(payload.slot, None)
        else:
            equipment[payload.slot] = stored_item
        setup.equipment = equipment
    elif payload.slot_type == "inventory":
        if not isinstance(payload.slot, int) or not (0 <= payload.slot < INVENTORY_SIZE):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"slot must be an integer 0-{INVENTORY_SIZE - 1}",
            )
        inventory = list(setup.inventory or [None] * INVENTORY_SIZE)
        if len(inventory) != INVENTORY_SIZE:
            inventory = (inventory + [None] * INVENTORY_SIZE)[:INVENTORY_SIZE]
        inventory[payload.slot] = stored_item
        setup.inventory = inventory
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_type must be 'equipment' or 'inventory'")

    db.commit()
    return build_purchase_goals_state(db, game_account)


def _check_gear_slot(slot_type: str, slot: Any) -> None:
    """Slot-shape validation shared with set_gear_slot, applied by
    move_gear_slot_item to both source and destination slots.
    """
    if slot_type == "equipment":
        if slot not in GEAR_SETUP_EQUIPMENT_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"slot must be one of {GEAR_SETUP_EQUIPMENT_SLOTS}"
            )
    elif slot_type == "inventory":
        if not isinstance(slot, int) or not (0 <= slot < INVENTORY_SIZE):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"slot must be an integer 0-{INVENTORY_SIZE - 1}",
            )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_type must be 'equipment' or 'inventory'")


def _read_gear_slot(equipment: dict, inventory: list, slot_type: str, slot: Any) -> Optional[dict]:
    return equipment.get(slot) if slot_type == "equipment" else inventory[slot]


def _write_gear_slot(equipment: dict, inventory: list, slot_type: str, slot: Any, item: Optional[dict]) -> None:
    if slot_type == "equipment":
        if item is None:
            equipment.pop(slot, None)
        else:
            equipment[slot] = item
    else:
        inventory[slot] = item


@router.put("/api/gear-setups/{setup_id}/slot/move")
def move_gear_slot_item(
    setup_id: str,
    payload: MoveGearSlotItemRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Drag-and-drop: moves the item between slots (equipment or inventory),
    swapping with an occupied destination. Works on the raw stored shape so a
    combo's components move unchanged.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)

    _check_gear_slot(payload.from_slot_type, payload.from_slot)
    _check_gear_slot(payload.to_slot_type, payload.to_slot)

    if payload.from_slot_type == payload.to_slot_type and payload.from_slot == payload.to_slot:
        # Dropped a slot onto itself; nothing to do.
        return build_purchase_goals_state(db, game_account)

    # Fresh dict/list, not in-place mutation; see the IMPORTANT note on
    # GearSetup in app/models.py.
    equipment = dict(setup.equipment or {})
    inventory = list(setup.inventory or [None] * INVENTORY_SIZE)
    if len(inventory) != INVENTORY_SIZE:
        inventory = (inventory + [None] * INVENTORY_SIZE)[:INVENTORY_SIZE]

    from_item = _read_gear_slot(equipment, inventory, payload.from_slot_type, payload.from_slot)
    to_item = _read_gear_slot(equipment, inventory, payload.to_slot_type, payload.to_slot)

    _write_gear_slot(equipment, inventory, payload.to_slot_type, payload.to_slot, from_item)
    _write_gear_slot(equipment, inventory, payload.from_slot_type, payload.from_slot, to_item)

    setup.equipment = equipment
    setup.inventory = inventory
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.put("/api/gear-setups/{setup_id}/still-to-purchase-sort")
def set_still_to_purchase_sort(
    setup_id: str,
    payload: SetStillToPurchaseSortRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Switches the active "Still to Purchase" sort. Leaves
    still_to_purchase_custom_order untouched so a dragged order survives mode
    switches.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.still_to_purchase_sort_mode = payload.sort_mode
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.put("/api/gear-setups/{setup_id}/still-to-purchase-order")
def set_still_to_purchase_order(
    setup_id: str,
    payload: SetStillToPurchaseOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a reorder of a setup's "Still to Purchase" list (payload.order is
    the full displayed list). Also switches to "custom" mode as a backstop.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.still_to_purchase_sort_mode = "custom"
    setup.still_to_purchase_custom_order = [
        {"slotType": entry.slot_type, "slot": entry.slot} for entry in payload.order
    ]
    db.commit()
    return build_purchase_goals_state(db, game_account)


@router.post("/api/gear-setups/{setup_id}/share")
def create_purchase_goal_share(
    setup_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes one gear setup into a SharedContent row
    (build_purchase_goal_share_snapshot in app/purchase_goals.py) and returns
    a myscape.io/s/<code> link; same posture as POST
    /api/players/me/loot/share.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    snapshot = build_purchase_goal_share_snapshot(setup)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="purchase_goal",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}
