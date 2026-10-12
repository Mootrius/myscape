"""Plugin sync and read endpoints for the current player and every item storage (bank, inventory, equipment, ...)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    get_current_game_account_from_api_key,
    get_current_verified_game_account_from_session,
)
from app.database import get_db
from app.item_ids import canonical_master_scroll_item_id
from app.models import (
    BankItem,
    BoatCargoItem,
    EquipmentItem,
    ForestryKitItem,
    GameAccount,
    HuntsmansKitItem,
    InventoryItem,
    LootingBagItem,
    MasterScrollBookItem,
    PohItem,
    PotionStorageItem,
    RunePouchItem,
    SeedBoxItem,
    SeedVaultItem,
    TackleBoxItem,
)
from app.routers import linking
from app.schemas import (
    EQUIPMENT_SLOTS,
    INVENTORY_SIZE,
    POSSESSION_STORAGE_KEYS,
    BankItemOut,
    BankOut,
    BankSyncRequest,
    BankSyncResponse,
    BoatCargoItemOut,
    BoatCargoOut,
    BoatCargoSyncRequest,
    BoatCargoSyncResponse,
    EquipmentItemOut,
    EquipmentOut,
    EquipmentSyncRequest,
    EquipmentSyncResponse,
    ForestryKitItemOut,
    ForestryKitOut,
    ForestryKitSyncRequest,
    ForestryKitSyncResponse,
    HuntsmansKitItemOut,
    HuntsmansKitOut,
    HuntsmansKitSyncRequest,
    HuntsmansKitSyncResponse,
    InventoryItemOut,
    InventoryOut,
    InventorySyncRequest,
    InventorySyncResponse,
    LootingBagItemOut,
    LootingBagOut,
    LootingBagSyncRequest,
    LootingBagSyncResponse,
    MasterScrollBookItemOut,
    MasterScrollBookOut,
    MasterScrollBookSyncRequest,
    MasterScrollBookSyncResponse,
    PlayerOut,
    PohItemOut,
    PohOut,
    PohSyncRequest,
    PohSyncResponse,
    PotionStorageItemOut,
    PotionStorageOut,
    PotionStorageSyncRequest,
    PotionStorageSyncResponse,
    RunePouchItemOut,
    RunePouchOut,
    RunePouchSyncRequest,
    RunePouchSyncResponse,
    SeedBoxItemOut,
    SeedBoxOut,
    SeedBoxSyncRequest,
    SeedBoxSyncResponse,
    SeedVaultItemOut,
    SeedVaultOut,
    SeedVaultSyncRequest,
    SeedVaultSyncResponse,
    SyncStatusOut,
    TackleBoxItemOut,
    TackleBoxOut,
    TackleBoxSyncRequest,
    TackleBoxSyncResponse,
)

router = APIRouter()


# Defensive upper bound, not a real OSRS limit: only a malformed or buggy client
# would hit it, and rejecting beats storing it.
MAX_BANK_ITEMS = 2000
# Inventory and equipment are fixed-size containers (28 and 11 slots), so these
# are exact ceilings.
MAX_INVENTORY_ITEMS = INVENTORY_SIZE
MAX_EQUIPMENT_ITEMS = len(EQUIPMENT_SLOTS)
# At most two rows per potion type (full-dose count plus one partial-dose item);
# generous multiple of a few dozen types.
MAX_POTION_STORAGE_ITEMS = 200
# A Rune Pouch has at most 6 slots (one rune type each), with a little headroom
# in case Jagex ships a bigger one.
MAX_RUNE_POUCH_ITEMS = 10
# Every tradeable seed (a few dozen types); generous multiple of the real
# ceiling.
MAX_SEED_VAULT_ITEMS = 200
# The Looting Bag holds up to 28 stacks, same as the inventory.
MAX_LOOTING_BAG_ITEMS = INVENTORY_SIZE
# A Tackle Box stores 35 distinct kinds of item; small headroom past that.
MAX_TACKLE_BOX_ITEMS = 50
# The whole PoH Costume Room as one sync (see PohItem in app/models.py), sized
# generously for all six furniture pieces combined.
MAX_POH_ITEMS = 1500
# A handful of Forestry event consumables at most; generous headroom.
MAX_FORESTRY_KIT_ITEMS = 50
# Dozens of distinct teleport scroll types; generous headroom.
MAX_MASTER_SCROLL_BOOK_ITEMS = 150
# The Seed Box holds six seed types; headroom in case that is raised.
MAX_SEED_BOX_ITEMS = 20
# A handful of creature-specific Hunter equipment sets; generous headroom.
MAX_HUNTSMANS_KIT_ITEMS = 50
# Bounds ONE boat slot's request, not all five boats (see sync_boat_cargo).
MAX_BOAT_CARGO_ITEMS = 100


@router.get("/api/players/me", response_model=PlayerOut)
def read_current_player(game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """The plugin calls this (`Authorization: Bearer <key>`) to confirm it is
    linked and to whom. Built by hand because email lives on the Account row
    (see app/routers/auth.py's _player_out_for).
    """
    return PlayerOut(
        id=game_account.id,
        email=game_account.account.email,
        runescape_name=game_account.runescape_name,
        account_hash=game_account.account_hash,
    )


@router.post("/api/players/me/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_player(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """Called by the plugin's "Unlink" button (API-key authenticated); see
    linking.revoke_link() for the session-authenticated counterpart.
    """
    linking.revoke_link(db, game_account)


def _stamp_storage_synced(game_account: GameAccount, storage_key: str, now: datetime) -> None:
    """Records that `storage_key` (a POSSESSION_STORAGE_KEYS entry) was just
    synced; called before each handler's db.commit() (see
    GameAccount.storage_synced_at). Reassigns the dict because SQLAlchemy
    doesn't track in-place mutation of a JSONB column.
    """
    game_account.storage_synced_at = {**(game_account.storage_synced_at or {}), storage_key: now.isoformat()}


@router.post("/api/players/me/bank", response_model=BankSyncResponse)
def sync_bank(
    payload: BankSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Called by the plugin (API-key authenticated) when the bank contents
    settle. A full replace, never a merge, so sold or withdrawn items
    disappear (see BankItem in app/models.py).
    """
    if len(payload.items) > MAX_BANK_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_BANK_ITEMS}).",
        )

    db.query(BankItem).filter(BankItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(BankItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "bank", now)
    db.commit()

    return BankSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/bank", response_model=BankOut)
def read_bank(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the last-synced bank snapshot
    (session-authenticated, unlike the POST above).
    """
    items = db.query(BankItem).filter(BankItem.game_account_id == game_account.id).order_by(BankItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return BankOut(items=[BankItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/inventory", response_model=InventorySyncResponse)
def sync_inventory(
    payload: InventorySyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for the 28-slot inventory."""
    if len(payload.items) > MAX_INVENTORY_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_INVENTORY_ITEMS}).",
        )

    db.query(InventoryItem).filter(InventoryItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(InventoryItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "inventory", now)
    db.commit()

    return InventorySyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/inventory", response_model=InventoryOut)
def read_inventory(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the inventory."""
    items = db.query(InventoryItem).filter(InventoryItem.game_account_id == game_account.id).order_by(InventoryItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return InventoryOut(items=[InventoryItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/equipment", response_model=EquipmentSyncResponse)
def sync_equipment(
    payload: EquipmentSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for worn equipment, keyed by
    slot.
    """
    if len(payload.items) > MAX_EQUIPMENT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_EQUIPMENT_ITEMS}).",
        )

    db.query(EquipmentItem).filter(EquipmentItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(EquipmentItem(
            game_account_id=game_account.id, slot=item.slot, item_id=item.item_id,
            item_name=item.item_name, quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "equipment", now)
    db.commit()

    return EquipmentSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/equipment", response_model=EquipmentOut)
def read_equipment(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for worn equipment."""
    items = db.query(EquipmentItem).filter(EquipmentItem.game_account_id == game_account.id).order_by(EquipmentItem.slot).all()
    updated_at = items[0].updated_at if items else None
    return EquipmentOut(items=[EquipmentItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/potion-storage", response_model=PotionStorageSyncResponse)
def sync_potion_storage(
    payload: PotionStorageSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for Potion Storage."""
    if len(payload.items) > MAX_POTION_STORAGE_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_POTION_STORAGE_ITEMS}).",
        )

    db.query(PotionStorageItem).filter(PotionStorageItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(PotionStorageItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "potion_storage", now)
    db.commit()

    return PotionStorageSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/potion-storage", response_model=PotionStorageOut)
def read_potion_storage(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for potion storage."""
    items = (
        db.query(PotionStorageItem)
        .filter(PotionStorageItem.game_account_id == game_account.id)
        .order_by(PotionStorageItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return PotionStorageOut(items=[PotionStorageItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/rune-pouch", response_model=RunePouchSyncResponse)
def sync_rune_pouch(
    payload: RunePouchSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for a Rune Pouch. Its own
    endpoint rather than part of /inventory's payload (see RunePouchItem in
    app/models.py).
    """
    if len(payload.items) > MAX_RUNE_POUCH_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_RUNE_POUCH_ITEMS}).",
        )

    db.query(RunePouchItem).filter(RunePouchItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(RunePouchItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "rune_pouch", now)
    db.commit()

    return RunePouchSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/rune-pouch", response_model=RunePouchOut)
def read_rune_pouch(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the rune pouch."""
    items = (
        db.query(RunePouchItem)
        .filter(RunePouchItem.game_account_id == game_account.id)
        .order_by(RunePouchItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return RunePouchOut(items=[RunePouchItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/seed-vault", response_model=SeedVaultSyncResponse)
def sync_seed_vault(
    payload: SeedVaultSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for a Seed Vault (see
    SeedVaultItem in app/models.py).
    """
    if len(payload.items) > MAX_SEED_VAULT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_SEED_VAULT_ITEMS}).",
        )

    db.query(SeedVaultItem).filter(SeedVaultItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(SeedVaultItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "seed_vault", now)
    db.commit()

    return SeedVaultSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/seed-vault", response_model=SeedVaultOut)
def read_seed_vault(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the seed vault."""
    items = (
        db.query(SeedVaultItem)
        .filter(SeedVaultItem.game_account_id == game_account.id)
        .order_by(SeedVaultItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return SeedVaultOut(items=[SeedVaultItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/looting-bag", response_model=LootingBagSyncResponse)
def sync_looting_bag(
    payload: LootingBagSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for a Looting Bag (see
    LootingBagItem in app/models.py).
    """
    if len(payload.items) > MAX_LOOTING_BAG_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_LOOTING_BAG_ITEMS}).",
        )

    db.query(LootingBagItem).filter(LootingBagItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(LootingBagItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "looting_bag", now)
    db.commit()

    return LootingBagSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/looting-bag", response_model=LootingBagOut)
def read_looting_bag(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the looting bag."""
    items = (
        db.query(LootingBagItem)
        .filter(LootingBagItem.game_account_id == game_account.id)
        .order_by(LootingBagItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return LootingBagOut(items=[LootingBagItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/tackle-box", response_model=TackleBoxSyncResponse)
def sync_tackle_box(
    payload: TackleBoxSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for a Tackle Box (see
    TackleBoxItem in app/models.py).
    """
    if len(payload.items) > MAX_TACKLE_BOX_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_TACKLE_BOX_ITEMS}).",
        )

    db.query(TackleBoxItem).filter(TackleBoxItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(TackleBoxItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "tackle_box", now)
    db.commit()

    return TackleBoxSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/tackle-box", response_model=TackleBoxOut)
def read_tackle_box(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the Tackle Box."""
    items = (
        db.query(TackleBoxItem)
        .filter(TackleBoxItem.game_account_id == game_account.id)
        .order_by(TackleBoxItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return TackleBoxOut(items=[TackleBoxItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/poh", response_model=PohSyncResponse)
def sync_poh(
    payload: PohSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for the whole PoH Costume
    Room: one endpoint for all six furniture pieces, named "poh" (see PohItem
    in app/models.py).
    """
    if len(payload.items) > MAX_POH_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_POH_ITEMS}).",
        )

    db.query(PohItem).filter(PohItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(PohItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "poh", now)
    db.commit()

    return PohSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/poh", response_model=PohOut)
def read_poh(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the PoH Costume Room."""
    items = (
        db.query(PohItem)
        .filter(PohItem.game_account_id == game_account.id)
        .order_by(PohItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return PohOut(items=[PohItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/forestry-kit", response_model=ForestryKitSyncResponse)
def sync_forestry_kit(
    payload: ForestryKitSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for the Forestry Kit (see
    ForestryKitItem in app/models.py).
    """
    if len(payload.items) > MAX_FORESTRY_KIT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_FORESTRY_KIT_ITEMS}).",
        )

    db.query(ForestryKitItem).filter(ForestryKitItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(ForestryKitItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "forestry_kit", now)
    db.commit()

    return ForestryKitSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/forestry-kit", response_model=ForestryKitOut)
def read_forestry_kit(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the Forestry Kit."""
    items = (
        db.query(ForestryKitItem)
        .filter(ForestryKitItem.game_account_id == game_account.id)
        .order_by(ForestryKitItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return ForestryKitOut(items=[ForestryKitItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/master-scroll-book", response_model=MasterScrollBookSyncResponse)
def sync_master_scroll_book(
    payload: MasterScrollBookSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for the Master Scroll Book
    (see MasterScrollBookItem). The container id is unconfirmed, so real syncs
    may not arrive yet.
    """
    if len(payload.items) > MAX_MASTER_SCROLL_BOOK_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_MASTER_SCROLL_BOOK_ITEMS}).",
        )

    db.query(MasterScrollBookItem).filter(MasterScrollBookItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    # The Book shows its default teleport under an untradeable cosmetic id;
    # store the real scroll id (canonical_master_scroll_item_id), merging rows
    # that collapse together so the unique constraint holds.
    merged_scrolls = {}
    for item in payload.items:
        real_id = canonical_master_scroll_item_id(item.item_id, item.item_name)
        if real_id in merged_scrolls:
            merged_scrolls[real_id]["quantity"] += item.quantity
        else:
            merged_scrolls[real_id] = {"item_name": item.item_name, "quantity": item.quantity}
    for real_id, scroll in merged_scrolls.items():
        db.add(MasterScrollBookItem(
            game_account_id=game_account.id, item_id=real_id, item_name=scroll["item_name"],
            quantity=scroll["quantity"], updated_at=now,
        ))
    _stamp_storage_synced(game_account, "master_scroll_book", now)
    db.commit()

    return MasterScrollBookSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/master-scroll-book", response_model=MasterScrollBookOut)
def read_master_scroll_book(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the Master Scroll Book."""
    items = (
        db.query(MasterScrollBookItem)
        .filter(MasterScrollBookItem.game_account_id == game_account.id)
        .order_by(MasterScrollBookItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return MasterScrollBookOut(items=[MasterScrollBookItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/seed-box", response_model=SeedBoxSyncResponse)
def sync_seed_box(
    payload: SeedBoxSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for the Seed Box (see
    SeedBoxItem in app/models.py).
    """
    if len(payload.items) > MAX_SEED_BOX_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_SEED_BOX_ITEMS}).",
        )

    db.query(SeedBoxItem).filter(SeedBoxItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(SeedBoxItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "seed_box", now)
    db.commit()

    return SeedBoxSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/seed-box", response_model=SeedBoxOut)
def read_seed_box(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the Seed Box."""
    items = (
        db.query(SeedBoxItem)
        .filter(SeedBoxItem.game_account_id == game_account.id)
        .order_by(SeedBoxItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return SeedBoxOut(items=[SeedBoxItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/huntsmans-kit", response_model=HuntsmansKitSyncResponse)
def sync_huntsmans_kit(
    payload: HuntsmansKitSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for a Huntsman's Kit (see
    HuntsmansKitItem in app/models.py).
    """
    if len(payload.items) > MAX_HUNTSMANS_KIT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_HUNTSMANS_KIT_ITEMS}).",
        )

    db.query(HuntsmansKitItem).filter(HuntsmansKitItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(HuntsmansKitItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "huntsmans_kit", now)
    db.commit()

    return HuntsmansKitSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/huntsmans-kit", response_model=HuntsmansKitOut)
def read_huntsmans_kit(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the Huntsman's Kit."""
    items = (
        db.query(HuntsmansKitItem)
        .filter(HuntsmansKitItem.game_account_id == game_account.id)
        .order_by(HuntsmansKitItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return HuntsmansKitOut(items=[HuntsmansKitItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.post("/api/players/me/boat-cargo/{slot}", response_model=BoatCargoSyncResponse)
def sync_boat_cargo(
    slot: int,
    payload: BoatCargoSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for ONE boat's cargo; `slot`
    (1-5) picks the boat and only that slot's rows are replaced (see
    BoatCargoItem).
    """
    if slot < 1 or slot > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot must be between 1 and 5.")
    if len(payload.items) > MAX_BOAT_CARGO_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_BOAT_CARGO_ITEMS}).",
        )

    db.query(BoatCargoItem).filter(BoatCargoItem.game_account_id == game_account.id, BoatCargoItem.slot == slot).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(BoatCargoItem(
            game_account_id=game_account.id, slot=slot, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    # One shared "boat_cargo" timestamp for all five slots, bumped by the latest
    # sync.
    _stamp_storage_synced(game_account, "boat_cargo", now)
    db.commit()

    return BoatCargoSyncResponse(item_count=len(payload.items))


@router.get("/api/players/me/boat-cargo", response_model=BoatCargoOut)
def read_boat_cargo(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for all boats combined, ordered
    by slot then item id (see BoatCargoItemOut).
    """
    items = (
        db.query(BoatCargoItem)
        .filter(BoatCargoItem.game_account_id == game_account.id)
        .order_by(BoatCargoItem.slot, BoatCargoItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return BoatCargoOut(items=[BoatCargoItemOut.model_validate(item) for item in items], updated_at=updated_at)


@router.get("/api/players/me/sync-status", response_model=SyncStatusOut)
def read_sync_status(game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """API-key authenticated because the plugin's side panel polls it. Returns
    every POSSESSION_STORAGE_KEYS entry, `None` if never synced (distinct from
    "synced empty").
    """
    stamped = game_account.storage_synced_at or {}
    return SyncStatusOut(storages={key: stamped.get(key) for key in POSSESSION_STORAGE_KEYS})
