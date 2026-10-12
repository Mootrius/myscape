"""Storages Viewer endpoints: trackers, pins, hidden storages, views and sharing."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_verified_game_account_from_session
from app.database import get_db
from app.models import (
    GameAccount,
    PinnedPossessionItem,
    PossessionTracker,
    PossessionView,
    SharedContent,
    _utcnow,
)
from app.pages import _SITE_URL
from app.possessions import (
    build_possession_views,
    build_possessions_share_snapshot,
    build_possessions_summary,
    build_trackers_state,
    hidden_storage_keys,
    next_possession_view_sort_order,
    next_sort_order,
    pinned_item_ids,
    search_trackable_items,
    set_storage_hidden,
)
from app.schemas import (
    POSSESSION_STORAGE_KEYS,
    ItemSearchResponse,
    PossessionShareCreateRequest,
    PossessionTrackerIn,
    PossessionTrackerUpdate,
    PossessionViewSaveRequest,
    PossessionViewUpdateRequest,
    SetPossessionViewOrderRequest,
)
from app.sharing import SHARE_DEFAULT_LIFETIME, generate_share_code

router = APIRouter()


@router.get("/api/possessions/search-items", response_model=ItemSearchResponse)
def possessions_item_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the tracker "add an item" search; every result has a real item id
    (search_trackable_items), which a tracker needs.
    """
    return ItemSearchResponse(results=search_trackable_items(q))


@router.get("/api/possessions/summary")
def possessions_summary(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Section 3's payload: every owned item, priced and broken down by location
    (build_possessions_summary). No response_model.
    """
    return build_possessions_summary(db, game_account)


@router.get("/api/possessions/trackers")
def possessions_trackers(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Sections 1/2's payload: the minimum and maximum trackers, each resolved
    against a live owned quantity (build_trackers_state in
    app/possessions.py).
    """
    return build_trackers_state(db, game_account)


@router.post("/api/possessions/trackers", status_code=status.HTTP_201_CREATED)
def create_possession_tracker(
    payload: PossessionTrackerIn,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Adds one min or max tracker. item_name is the untradeable-item display
    fallback (see BankItem). Re-adding an existing (kind, item_id) updates its
    target.
    """
    existing = (
        db.query(PossessionTracker)
        .filter(
            PossessionTracker.game_account_id == game_account.id,
            PossessionTracker.kind == payload.kind,
            PossessionTracker.item_id == payload.item_id,
        )
        .first()
    )
    if existing:
        existing.target_quantity = payload.target_quantity
        if payload.item_name:
            existing.item_name = payload.item_name
        db.commit()
    else:
        db.add(PossessionTracker(
            game_account_id=game_account.id,
            kind=payload.kind,
            item_id=payload.item_id,
            item_name=payload.item_name,
            target_quantity=payload.target_quantity,
            sort_order=next_sort_order(db, game_account, payload.kind),
        ))
        db.commit()
    return build_trackers_state(db, game_account)


@router.patch("/api/possessions/trackers/{tracker_id}")
def update_possession_tracker(
    tracker_id: uuid.UUID,
    payload: PossessionTrackerUpdate,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Edits a tracker's target quantity in place; swapping the item is
    delete-and-recreate (see PossessionTrackerUpdate in app/schemas.py).
    """
    tracker = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.id == tracker_id, PossessionTracker.game_account_id == game_account.id)
        .first()
    )
    if not tracker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found.")
    tracker.target_quantity = payload.target_quantity
    db.commit()
    return build_trackers_state(db, game_account)


@router.delete("/api/possessions/trackers/{tracker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_possession_tracker(
    tracker_id: uuid.UUID,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    tracker = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.id == tracker_id, PossessionTracker.game_account_id == game_account.id)
        .first()
    )
    if not tracker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found.")
    db.delete(tracker)
    db.commit()


@router.post("/api/possessions/pins/{item_id}")
def pin_possession_item(
    item_id: int,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Pins one item to the top of section 3 (see PinnedPossessionItem).
    Idempotent.
    """
    existing = (
        db.query(PinnedPossessionItem)
        .filter(PinnedPossessionItem.game_account_id == game_account.id, PinnedPossessionItem.item_id == item_id)
        .first()
    )
    if not existing:
        db.add(PinnedPossessionItem(game_account_id=game_account.id, item_id=item_id))
        db.commit()
    return {"pinnedItemIds": sorted(pinned_item_ids(db, game_account))}


@router.delete("/api/possessions/pins/{item_id}")
def unpin_possession_item(
    item_id: int,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Unpins one item; idempotent like pin_possession_item."""
    db.query(PinnedPossessionItem).filter(
        PinnedPossessionItem.game_account_id == game_account.id, PinnedPossessionItem.item_id == item_id
    ).delete()
    db.commit()
    return {"pinnedItemIds": sorted(pinned_item_ids(db, game_account))}


@router.post("/api/possessions/hidden-storages/{storage_key}")
def hide_possession_storage(
    storage_key: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Switches one storage source off (see HiddenPossessionStorage); its items
    stop counting toward section 3 and tracker quantities.
    """
    if storage_key not in POSSESSION_STORAGE_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown storage.")
    set_storage_hidden(db, game_account, storage_key, True)
    return {"hiddenStorageKeys": sorted(hidden_storage_keys(db, game_account))}


@router.delete("/api/possessions/hidden-storages/{storage_key}")
def unhide_possession_storage(
    storage_key: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Reverses hide_possession_storage; idempotent like unpin_possession_item."""
    if storage_key not in POSSESSION_STORAGE_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown storage.")
    set_storage_hidden(db, game_account, storage_key, False)
    return {"hiddenStorageKeys": sorted(hidden_storage_keys(db, game_account))}


@router.post("/api/possessions/share")
def create_possessions_share(
    payload: PossessionShareCreateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes section 3 into a SharedContent row
    (build_possessions_share_snapshot) and returns a myscape.io/s/<code> link.
    """
    snapshot = build_possessions_share_snapshot(db, game_account, payload.locations)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="possessions",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@router.get("/api/possessions/views")
def list_possession_views(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Every saved Storages Viewer view (build_possession_views in
    app/possessions.py), in reorder-strip order.
    """
    return {"views": build_possession_views(db, game_account)}


@router.post("/api/possessions/views", status_code=status.HTTP_201_CREATED)
def create_possession_view(
    payload: PossessionViewSaveRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves the current filter/sort setup as a new named view, always appended;
    renaming/overwriting is PATCH .../{view_id}.
    """
    db.add(PossessionView(
        game_account_id=game_account.id,
        name=payload.name,
        config=payload.config,
        sort_order=next_possession_view_sort_order(db, game_account),
    ))
    db.commit()
    return {"views": build_possession_views(db, game_account)}


@router.put("/api/possessions/views/order")
def set_possession_view_order(
    payload: SetPossessionViewOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a reorder of the saved-views strip (payload.order is the complete id
    list; omitted ids keep their sort_order, unowned ids are ignored).
    """
    owned_views = {
        str(v.id): v
        for v in db.query(PossessionView).filter(PossessionView.game_account_id == game_account.id).all()
    }
    for index, view_id in enumerate(payload.order):
        view = owned_views.get(view_id)
        if view is not None:
            view.sort_order = float(index)
    db.commit()
    return {"views": build_possession_views(db, game_account)}


def _get_owned_possession_view(db: Session, game_account: GameAccount, view_id: str) -> PossessionView:
    try:
        view_uuid = uuid.UUID(view_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found.")
    view = (
        db.query(PossessionView)
        .filter(PossessionView.id == view_uuid, PossessionView.game_account_id == game_account.id)
        .first()
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found.")
    return view


@router.patch("/api/possessions/views/{view_id}")
def update_possession_view(
    view_id: str,
    payload: PossessionViewUpdateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Renames a saved view, replaces its stored config, or both (see
    PossessionViewUpdateRequest in app/schemas.py).
    """
    view = _get_owned_possession_view(db, game_account, view_id)
    if payload.name is not None:
        view.name = payload.name
    if payload.config is not None:
        view.config = payload.config
    db.commit()
    return {"views": build_possession_views(db, game_account)}


@router.delete("/api/possessions/views/{view_id}")
def delete_possession_view(
    view_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    view = _get_owned_possession_view(db, game_account, view_id)
    db.delete(view)
    db.commit()
    return {"views": build_possession_views(db, game_account)}
