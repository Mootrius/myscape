"""myscape's web app: a placeholder landing page, health checks, and the
early account system (website signup/login, RuneLite plugin account
linking) -- see README.md for how the pieces fit together.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import (
    get_current_player_from_api_key,
    get_current_player_from_session,
    get_optional_current_player_from_session,
)
from app.database import get_db
from app.limiter import limiter
from app.loot import build_loot_state, sync_loot_events
from app.models import BankItem, EquipmentItem, GearSetup, InventoryItem, Player, PotionStorageItem, RunePouchItem
from app.pages import render_dashboard, render_landing, render_login, render_loot_tracker, render_purchase_goals, render_signup
from app.purchase_goals import (
    build_purchase_goals_state,
    get_mapping,
    is_crystal_armour_piece,
    is_elidinis_ward_f,
    is_faerdhinen_or_saeldor,
    search_items,
)
from app.recipes import expand_recipe_components
from app.routers import auth, linking
from app.schemas import (
    BankOut,
    BankItemOut,
    BankSyncRequest,
    BankSyncResponse,
    CreateGearSetupRequest,
    EquipmentOut,
    EquipmentItemOut,
    EquipmentSyncRequest,
    EquipmentSyncResponse,
    EQUIPMENT_SLOTS,
    GEAR_SETUP_EQUIPMENT_SLOTS,
    INVENTORY_SIZE,
    InventoryOut,
    InventoryItemOut,
    InventorySyncRequest,
    InventorySyncResponse,
    ItemSearchResponse,
    LootSyncRequest,
    LootSyncResponse,
    MoveGearSlotItemRequest,
    PlayerOut,
    PotionStorageOut,
    PotionStorageItemOut,
    PotionStorageSyncRequest,
    PotionStorageSyncResponse,
    RenameGearSetupRequest,
    RunePouchOut,
    RunePouchItemOut,
    RunePouchSyncRequest,
    RunePouchSyncResponse,
    SetGearSetupIconRequest,
    SetGearSlotRequest,
    SetStillToPurchaseOrderRequest,
    SetStillToPurchaseSortRequest,
)

# A defensive upper bound, not a real OSRS limit -- the largest bank
# ever seen is nowhere near this, so the only way a sync would hit it is
# a malformed or buggy client, and rejecting that outright beats quietly
# accepting and storing whatever it sent.
MAX_BANK_ITEMS = 2000
# The inventory and equipment containers are fixed-size (28 slots, 11
# slots), so unlike the bank there's a real upper bound on distinct
# items in one sync -- these are that exact size, not a round-number
# guess, so anything over is definitely malformed.
MAX_INVENTORY_ITEMS = INVENTORY_SIZE
MAX_EQUIPMENT_ITEMS = len(EQUIPMENT_SLOTS)
# Potion Storage supports a few dozen distinct potion types, and the
# plugin reports at most two rows per type (a full-dose count plus one
# leftover partial-dose item -- see MyscapePlugin#readPotionStorageItems
# in the Mootrius/myscape-plugin repo), so this is a generous multiple
# of the real ceiling, not a round-number guess either.
MAX_POTION_STORAGE_ITEMS = 200
# A Rune Pouch (regular or Divine) has at most 6 slots (see
# MyscapePlugin's RUNE_POUCH_TYPE_VARBITS in the Mootrius/myscape-plugin
# repo, read defensively at 6 even though only 3-4 are used in-game
# today), each holding a single rune type -- so 6 is the real ceiling,
# not a round-number guess. Left with a little headroom in case Jagex
# ever ships a bigger pouch before this constant is revisited.
MAX_RUNE_POUCH_ITEMS = 10
# The plugin syncs one loot event immediately as it happens (see
# MyscapePlugin#onLootReceived), so a real sync is always exactly 1 --
# this is a defensive upper bound against a malformed/buggy client
# trying to batch an unreasonable number into one request, not a real
# expected size.
MAX_LOOT_EVENTS_PER_SYNC = 50

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "SESSION_SECRET_KEY is not set. Generate one (e.g. `python -c "
        "'import secrets; print(secrets.token_hex(32))'`) and set it as an "
        "environment variable -- see .env.example. On Render, render.yaml "
        "already has it set to auto-generate and persist a value."
    )

app = FastAPI(title="myscape")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Session cookies back website login (see app/auth.py). `https_only` is on
# because myscape.io is HTTPS-only in production; if that ever gets in the
# way of local http://localhost testing, override it with an env var --
# don't just delete it.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_HTTPS_ONLY", "true").lower() != "false",
    max_age=60 * 60 * 24 * 30,  # 30 days
)
app.include_router(auth.router)
app.include_router(linking.router)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.on_event("startup")
def on_startup():
    # Brings the database up to the latest schema by applying whichever
    # of migrations/versions/*.py it hasn't seen yet (see README.md's
    # "Database schema changes") -- the Alembic equivalent of the old
    # Base.metadata.create_all() + sync_missing_columns() pair this
    # replaced, which is also why this still runs unconditionally on
    # every startup rather than as a separate deploy step: it's the
    # smallest change from the previous behavior, and safe here since
    # this service only ever runs as a single instance. The very first
    # migration is written defensively (skips any table that already
    # exists) specifically so this needs no one-time manual step to
    # tell Alembic that production's existing tables are already
    # "migrated" -- see migrations/versions/5cf359e6d5b1_initial_schema.py.
    alembic_cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@app.get("/", response_class=HTMLResponse)
def root(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_landing(None)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_signup()


@app.get("/login", response_class=HTMLResponse)
def login_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_login()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_dashboard(player)


@app.get("/api/health")
def health():
    """Proves the app itself is up. Doesn't touch the database -- see
    /api/health/db for that -- so this stays fast and always answers even
    if the database is briefly unreachable."""
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    """Proves the app can actually reach and query the database -- the
    real end-to-end check for a first deploy."""
    player_count = db.execute(text("SELECT COUNT(*) FROM players")).scalar()
    return {"status": "ok", "playerCount": player_count}


@app.get("/api/players/me", response_model=PlayerOut)
def read_current_player(player: Player = Depends(get_current_player_from_api_key)):
    """First real use of the API key auth: the plugin calls this (with
    its `Authorization: Bearer <key>` header) to confirm it's linked and
    see which player it's linked to."""
    return player


@app.post("/api/players/me/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_player(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_api_key)):
    """Called by the RuneLite plugin's "Unlink" button (API-key
    authenticated). See linking.revoke_link() for what this actually
    does and why POST /api/link/unlink there is this endpoint's
    session-authenticated counterpart, not a duplicate."""
    linking.revoke_link(db, player)


@app.post("/api/players/me/bank", response_model=BankSyncResponse)
def sync_bank(
    payload: BankSyncRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_api_key),
):
    """Called by the RuneLite plugin (API-key authenticated) whenever
    the bank interface is open and its contents settle after a change
    -- see MyscapeClient#syncBank in the Mootrius/myscape-plugin repo.
    Always a full replace, never a merge: every one of the player's
    existing bank_items rows is deleted and replaced with exactly what
    this request says, so an item that's been sold or withdrawn since
    the last sync disappears here too, the same way it disappeared from
    the actual bank (see BankItem's docstring in app/models.py for why
    that's the right model for this)."""
    if len(payload.items) > MAX_BANK_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_BANK_ITEMS}).",
        )

    db.query(BankItem).filter(BankItem.player_id == player.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(BankItem(
            player_id=player.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    db.commit()

    return BankSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/bank", response_model=BankOut)
def read_bank(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """The website's own read of the last-synced bank snapshot --
    session-authenticated (unlike the POST above), since it's the
    website reading this back, not the plugin writing it. Nothing in
    the UI surfaces this yet (Purchase Goals is still a placeholder
    card on /dashboard), but this is what that card will eventually
    read from."""
    items = db.query(BankItem).filter(BankItem.player_id == player.id).order_by(BankItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return BankOut(items=[BankItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/inventory", response_model=InventorySyncResponse)
def sync_inventory(
    payload: InventorySyncRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the main
    28-slot inventory instead -- see MyscapeClient#syncInventory in the
    Mootrius/myscape-plugin repo. Full replace, never a merge."""
    if len(payload.items) > MAX_INVENTORY_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_INVENTORY_ITEMS}).",
        )

    db.query(InventoryItem).filter(InventoryItem.player_id == player.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(InventoryItem(
            player_id=player.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    db.commit()

    return InventorySyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/inventory", response_model=InventoryOut)
def read_inventory(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """Same contract as GET /api/players/me/bank above, for the
    inventory instead."""
    items = db.query(InventoryItem).filter(InventoryItem.player_id == player.id).order_by(InventoryItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return InventoryOut(items=[InventoryItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/equipment", response_model=EquipmentSyncResponse)
def sync_equipment(
    payload: EquipmentSyncRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for worn
    equipment instead -- see MyscapeClient#syncEquipment in the
    Mootrius/myscape-plugin repo. Full replace, never a merge, keyed by
    slot rather than item id (EquipmentSyncRequest's own validator
    already rejects a duplicate slot within one sync -- see
    app/schemas.py)."""
    if len(payload.items) > MAX_EQUIPMENT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_EQUIPMENT_ITEMS}).",
        )

    db.query(EquipmentItem).filter(EquipmentItem.player_id == player.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(EquipmentItem(
            player_id=player.id, slot=item.slot, item_id=item.item_id,
            item_name=item.item_name, quantity=item.quantity, updated_at=now,
        ))
    db.commit()

    return EquipmentSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/equipment", response_model=EquipmentOut)
def read_equipment(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """Same contract as GET /api/players/me/bank above, for worn
    equipment instead."""
    items = db.query(EquipmentItem).filter(EquipmentItem.player_id == player.id).order_by(EquipmentItem.slot).all()
    updated_at = items[0].updated_at if items else None
    return EquipmentOut(items=[EquipmentItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/potion-storage", response_model=PotionStorageSyncResponse)
def sync_potion_storage(
    payload: PotionStorageSyncRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the
    Player-Owned-House Potion Storage instead -- see
    MyscapeClient#syncPotionStorage in the Mootrius/myscape-plugin repo.
    Full replace, never a merge. Unlike bank/inventory/equipment,
    Potion Storage isn't an ItemContainer the plugin can just read
    directly -- see MyscapePlugin#readPotionStorageItems there for how
    it actually reads this -- but the resulting shape and this
    endpoint's contract are identical, so nothing here needs to know
    the difference. This is also what replaced the old "supplies"
    gear-slot flag: see PotionStorageItem's docstring in app/models.py
    for why that flag existed and why it's gone now."""
    if len(payload.items) > MAX_POTION_STORAGE_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_POTION_STORAGE_ITEMS}).",
        )

    db.query(PotionStorageItem).filter(PotionStorageItem.player_id == player.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(PotionStorageItem(
            player_id=player.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    db.commit()

    return PotionStorageSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/potion-storage", response_model=PotionStorageOut)
def read_potion_storage(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """Same contract as GET /api/players/me/bank above, for potion
    storage instead."""
    items = (
        db.query(PotionStorageItem)
        .filter(PotionStorageItem.player_id == player.id)
        .order_by(PotionStorageItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return PotionStorageOut(items=[PotionStorageItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/rune-pouch", response_model=RunePouchSyncResponse)
def sync_rune_pouch(
    payload: RunePouchSyncRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for a Rune
    Pouch's contents instead -- see MyscapeClient#syncRunePouch in the
    Mootrius/myscape-plugin repo. Full replace, never a merge. Unlike
    bank/inventory/equipment, a Rune Pouch's contents aren't part of any
    ItemContainer the plugin can just read directly -- see
    MyscapePlugin#readRunePouchItems there for how it actually reads
    this (the pouch itself is one inventory item; what's stored inside
    it comes from a separate set of varbits) -- but the resulting shape
    and this endpoint's contract are identical, so nothing here needs to
    know the difference. Deliberately its own endpoint rather than
    folded into /inventory's payload: see RunePouchItem's docstring in
    app/models.py for why."""
    if len(payload.items) > MAX_RUNE_POUCH_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_RUNE_POUCH_ITEMS}).",
        )

    db.query(RunePouchItem).filter(RunePouchItem.player_id == player.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(RunePouchItem(
            player_id=player.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    db.commit()

    return RunePouchSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/rune-pouch", response_model=RunePouchOut)
def read_rune_pouch(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """Same contract as GET /api/players/me/bank above, for the rune
    pouch instead."""
    items = (
        db.query(RunePouchItem)
        .filter(RunePouchItem.player_id == player.id)
        .order_by(RunePouchItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return RunePouchOut(items=[RunePouchItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/loot", response_model=LootSyncResponse)
def sync_loot(
    payload: LootSyncRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_api_key),
):
    """Records one or more loot events (a kill, a clue casket, a
    pickpocket -- see MyscapePlugin#onLootReceived in the
    Mootrius/myscape-plugin repo) as they happen. Unlike every sync
    endpoint above, this is an insert-if-new, not a delete-and-replace
    -- see LootEvent's docstring in app/models.py for why a historical
    log needs a different sync shape than a current-state snapshot, and
    sync_loot_events in app/loot.py for the actual dedup logic (keyed
    on each event's client-generated event_id)."""
    if len(payload.events) > MAX_LOOT_EVENTS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many events in one sync (max {MAX_LOOT_EVENTS_PER_SYNC}).",
        )
    added_count = sync_loot_events(db, player, payload.events)
    return LootSyncResponse(added_count=added_count)


@app.get("/api/players/me/loot")
def read_loot(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """The combined state the Loot Tracker page polls -- the rolling
    24-hour bar chart's buckets and a per-NPC breakdown of that same
    window, computed fresh from this player's synced LootEvent rows.
    Not pinned to a Pydantic response_model for the same reason GET
    /api/gear-setups above isn't -- see LootState's docstring in
    app/schemas.py. See build_loot_state in app/loot.py."""
    return build_loot_state(db, player)


@app.get("/api/items/search", response_model=ItemSearchResponse)
def item_search(q: str = "", player: Player = Depends(get_current_player_from_session)):
    """Backs the gear-setup slot picker's search box (see
    app/purchase_goals.py's search_items -- ported from Maintrius's own
    search_items in osrs_tracker.py) -- session-authenticated like every
    other Purchase Goals endpoint below, since only the website UI calls
    this, never the plugin."""
    return ItemSearchResponse(results=search_items(q))


@app.get("/dashboard/purchase-goals", response_class=HTMLResponse)
def purchase_goals_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_purchase_goals(player)


@app.get("/dashboard/loot", response_class=HTMLResponse)
def loot_tracker_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_loot_tracker(player)


@app.get("/api/gear-setups")
def list_gear_setups(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_session)):
    """The combined state the Purchase Goals page polls (see
    app/purchase_goals.py's build_purchase_goals_state, ported from
    Maintrius's own build_state in osrs_tracker.py) -- every one of the
    player's gear setups, fully priced/owned-checked against their
    synced bank+inventory+equipment+potion storage, plus their current coins and
    whatever wiki price/mapping errors are in effect. Not pinned to a
    Pydantic response_model (see GearSetupsState's docstring in
    app/schemas.py) since the shape is too dynamic/nested to usefully
    fix -- FastAPI serializes the plain dict build_purchase_goals_state
    returns as-is."""
    return build_purchase_goals_state(db, player)


@app.post("/api/gear-setups", status_code=status.HTTP_201_CREATED)
def create_gear_setup(
    payload: CreateGearSetupRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    name = (payload.name or "").strip() or "New Setup"
    setup = GearSetup(player_id=player.id, name=name, equipment={}, inventory=[None] * INVENTORY_SIZE)
    db.add(setup)
    db.commit()
    return build_purchase_goals_state(db, player)


def _get_owned_gear_setup(db: Session, player: Player, setup_id: str) -> GearSetup:
    try:
        setup_uuid = uuid.UUID(setup_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gear setup not found")
    setup = (
        db.query(GearSetup)
        .filter(GearSetup.id == setup_uuid, GearSetup.player_id == player.id)
        .first()
    )
    if setup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gear setup not found")
    return setup


@app.patch("/api/gear-setups/{setup_id}")
def rename_gear_setup(
    setup_id: str,
    payload: RenameGearSetupRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    setup = _get_owned_gear_setup(db, player, setup_id)
    setup.name = payload.name
    db.commit()
    return build_purchase_goals_state(db, player)


@app.delete("/api/gear-setups/{setup_id}")
def delete_gear_setup(
    setup_id: str,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    setup = _get_owned_gear_setup(db, player, setup_id)
    db.delete(setup)
    db.commit()
    return build_purchase_goals_state(db, player)


@app.put("/api/gear-setups/{setup_id}/icon")
def set_gear_setup_icon(
    setup_id: str,
    payload: SetGearSetupIconRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    """Sets (or, with icon omitted/null, clears) the display-only icon
    shown next to a setup's total cost -- purely cosmetic, never affects
    cost/ownership (see GearSetup's docstring in app/models.py and
    _handle_set_gear_setup_icon in Maintrius's own osrs_tracker.py)."""
    setup = _get_owned_gear_setup(db, player, setup_id)
    if payload.icon is None:
        setup.icon = None
    else:
        setup.icon = {"itemId": payload.icon.item_id, "itemName": payload.icon.item_name or None}
    db.commit()
    return build_purchase_goals_state(db, player)


@app.put("/api/gear-setups/{setup_id}/slot")
def set_gear_slot(
    setup_id: str,
    payload: SetGearSlotRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    """Fills (or, with item omitted/null, clears) one equipment or
    inventory slot of a gear setup -- see SetGearSlotRequest/
    GearSlotItemIn in app/schemas.py for the validated shape (plain
    tradeable, plain untradeable, or composed "combo") and
    _handle_set_gear_slot in Maintrius's own osrs_tracker.py for the
    original this ports. Stores exactly what was sent, unresolved --
    pricing/ownership is computed fresh on every read, not here (see
    app/purchase_goals.py) -- with one addition: a plain untradeable
    item (no item_id, no components) is checked against the known
    item-combination recipes (app/recipes.py) and, on a match, is
    auto-expanded into a "combo" here before it's ever persisted. This
    is what lets someone search for and select e.g. "Neitiznot
    faceguard" directly instead of having to know it's built from a
    Helm of Neitiznot + a Basilisk jaw and build it from parts
    themselves -- the frontend never has to know the difference."""
    setup = _get_owned_gear_setup(db, player, setup_id)

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
            and not is_crystal_armour_piece(payload.item.item_name)
            and not is_faerdhinen_or_saeldor(payload.item.item_name)
            and not is_elidinis_ward_f(payload.item.item_name)
        ):
            # Crystal helm/body/legs, Bow of Faerdhinen/Blade of
            # Saeldor, and Elidinis' ward (f) are skipped here -- the
            # wiki's own recipe data for the first two is unreliable,
            # and simply doesn't exist at all for the ward (see
            # _crystal_armour_seed_price's, _faerdhinen_saeldor_price's,
            # and _elidinis_ward_f_price's docstrings in
            # app/purchase_goals.py), and they're priced against the
            # relevant seed(s)/ingredients directly at read time
            # instead, so there's nothing useful to auto-expand into up
            # front.
            mapping, _ = get_mapping()
            auto_components = expand_recipe_components(payload.item.item_name, mapping)
            if auto_components:
                stored_item["components"] = auto_components

    if payload.slot_type == "equipment":
        if payload.slot not in GEAR_SETUP_EQUIPMENT_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"slot must be one of {GEAR_SETUP_EQUIPMENT_SLOTS}"
            )
        # New dict, not an in-place mutation of the loaded one -- see the
        # IMPORTANT note on GearSetup in app/models.py for why that
        # distinction matters for a JSONB column.
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
    return build_purchase_goals_state(db, player)


def _check_gear_slot(slot_type: str, slot: Any) -> None:
    """Same slot-shape validation set_gear_slot applies to the one slot
    it's writing, factored out so move_gear_slot_item below can apply it
    to both the source and destination slot of a drag-and-drop."""
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


@app.put("/api/gear-setups/{setup_id}/slot/move")
def move_gear_slot_item(
    setup_id: str,
    payload: MoveGearSlotItemRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    """Drag-and-drop: moves whatever's stored in (from_slot_type,
    from_slot) into (to_slot_type, to_slot), across equipment and
    inventory alike. If the destination already holds an item, the two
    simply swap rather than the destination's original item being lost.

    Operates purely on the raw stored shape (exactly what set_gear_slot
    itself would have stored -- item id/name, or a combo's already-
    expanded components list), never on the resolved/priced shape the
    frontend renders -- so a combo's exact stored components move
    across untouched rather than being reconstructed from (and
    potentially drifting from) their priced/resolved form."""
    setup = _get_owned_gear_setup(db, player, setup_id)

    _check_gear_slot(payload.from_slot_type, payload.from_slot)
    _check_gear_slot(payload.to_slot_type, payload.to_slot)

    if payload.from_slot_type == payload.to_slot_type and payload.from_slot == payload.to_slot:
        # Dropped a slot onto itself -- nothing to do.
        return build_purchase_goals_state(db, player)

    # Fresh dict/list, not an in-place mutation of the loaded ones -- see
    # the IMPORTANT note on GearSetup in app/models.py for why that
    # distinction matters for a JSONB column.
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
    return build_purchase_goals_state(db, player)


@app.put("/api/gear-setups/{setup_id}/still-to-purchase-sort")
def set_still_to_purchase_sort(
    setup_id: str,
    payload: SetStillToPurchaseSortRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    """Switches which of the buttons above a setup's "Still to
    Purchase" list is active -- see STILL_TO_PURCHASE_SORT_MODES in
    app/schemas.py and _still_to_purchase_summary in
    app/purchase_goals.py for what each one actually does. Doesn't
    touch still_to_purchase_custom_order -- switching to "custom" and
    back doesn't lose a previously-dragged order, and switching away
    from "custom" doesn't erase it either, it's just not applied while
    a different mode is active."""
    setup = _get_owned_gear_setup(db, player, setup_id)
    setup.still_to_purchase_sort_mode = payload.sort_mode
    db.commit()
    return build_purchase_goals_state(db, player)


@app.put("/api/gear-setups/{setup_id}/still-to-purchase-order")
def set_still_to_purchase_order(
    setup_id: str,
    payload: SetStillToPurchaseOrderRequest,
    db: Session = Depends(get_db),
    player: Player = Depends(get_current_player_from_session),
):
    """Saves a drag-and-drop reorder of a setup's "Still to Purchase"
    list -- payload.order is the complete list as currently displayed
    (not a delta), one {slot_type, slot} entry per row, exactly mirroring
    how set_gear_slot/move_gear_slot_item always store a full
    replacement rather than a patch. Also switches the setup into
    "custom" sort mode if it wasn't already there -- dragging a row is
    only ever possible in "custom" mode client-side (see
    renderSummaryList in app/pages.py), so this is a defensive
    backstop, not something a well-behaved client should ever rely on."""
    setup = _get_owned_gear_setup(db, player, setup_id)
    setup.still_to_purchase_sort_mode = "custom"
    setup.still_to_purchase_custom_order = [
        {"slotType": entry.slot_type, "slot": entry.slot} for entry in payload.order
    ]
    db.commit()
    return build_purchase_goals_state(db, player)
