"""Loot Tracker sync, read, share and hide endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    get_current_game_account_from_api_key,
    get_current_verified_game_account_from_session,
)
from app.database import get_db
from app.loot import (
    build_loot_share_snapshot,
    build_loot_state,
    parse_loot_range_bound,
    resolve_range,
    set_item_hidden,
    set_npc_hidden,
    sync_loot_events,
)
from app.models import (
    GameAccount,
    SharedContent,
    _utcnow,
)
from app.pages import _SITE_URL
from app.schemas import (
    HideLootItemRequest,
    HideLootNpcRequest,
    LootShareCreateRequest,
    LootSyncRequest,
    LootSyncResponse,
)
from app.sharing import SHARE_DEFAULT_LIFETIME, generate_share_code

router = APIRouter()


# The plugin syncs one loot event as it happens, so a real sync is exactly 1;
# this is a defensive bound against batching abuse.
MAX_LOOT_EVENTS_PER_SYNC = 50


@router.post("/api/players/me/loot", response_model=LootSyncResponse)
def sync_loot(
    payload: LootSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Records loot events as they happen. Insert-if-new, not delete-and-replace;
    dedup keys on the client-generated event_id (sync_loot_events in
    app/loot.py).
    """
    if len(payload.events) > MAX_LOOT_EVENTS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many events in one sync (max {MAX_LOOT_EVENTS_PER_SYNC}).",
        )
    added_count = sync_loot_events(db, game_account, payload.events)
    return LootSyncResponse(added_count=added_count)


@router.get("/api/players/me/loot")
def read_loot(
    range: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """The Loot Tracker's polled state (build_loot_state in app/loot.py). `range`
    is a RANGE_PRESETS key or "custom"; custom `start`/`end` are "YYYY-MM-DD"
    dates (both inclusive) or ISO-8601 timestamps (a clicked bar's bucket; see
    parse_loot_range_bound). Unrecognized or incomplete ranges fall back to
    resolve_range's 24-hour default. No response_model (see LootState).
    """
    start_dt = None
    end_dt = None
    if range == "custom":
        try:
            if start:
                start_dt = parse_loot_range_bound(start, is_end=False)
            if end:
                end_dt = parse_loot_range_bound(end, is_end=True)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start/end must be YYYY-MM-DD dates or ISO-8601 timestamps.",
            )
    range_start, range_end = resolve_range(range, start_dt, end_dt)
    return build_loot_state(db, game_account, range_start, range_end)


@router.post("/api/players/me/loot/share")
def create_loot_share(
    payload: LootShareCreateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes the selected range into a SharedContent row
    (build_loot_share_snapshot in app/loot.py) and returns a
    myscape.io/s/<code> link. Unthrottled: GET /s/{code} is the rate-limited
    surface.
    """
    start_dt = None
    end_dt = None
    if payload.range == "custom":
        try:
            if payload.start:
                start_dt = parse_loot_range_bound(payload.start, is_end=False)
            if payload.end:
                end_dt = parse_loot_range_bound(payload.end, is_end=True)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start/end must be YYYY-MM-DD dates or ISO-8601 timestamps.",
            )
    range_start, range_end = resolve_range(payload.range, start_dt, end_dt)
    snapshot = build_loot_share_snapshot(db, game_account, range_start, range_end)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="loot_tracker",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@router.post("/api/players/me/loot/hidden-npcs")
def hide_loot_npc(payload: HideLootNpcRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Hides one NPC from Loot Tracker (the eye button on an NPC tile); see
    set_npc_hidden in app/loot.py.
    """
    set_npc_hidden(db, game_account, payload.name, True)
    return {"ok": True}


@router.delete("/api/players/me/loot/hidden-npcs")
def unhide_loot_npc(payload: HideLootNpcRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Reverses hide_loot_npc."""
    set_npc_hidden(db, game_account, payload.name, False)
    return {"ok": True}


@router.post("/api/players/me/loot/hidden-items")
def hide_loot_item(payload: HideLootItemRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Hides one item from Loot Tracker (see set_item_hidden in app/loot.py)."""
    set_item_hidden(db, game_account, payload.item_id, payload.item_name, True)
    return {"ok": True}


@router.delete("/api/players/me/loot/hidden-items")
def unhide_loot_item(payload: HideLootItemRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Reverses hide_loot_item."""
    set_item_hidden(db, game_account, payload.item_id, payload.item_name, False)
    return {"ok": True}
