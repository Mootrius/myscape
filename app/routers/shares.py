"""Shared-content page (/s/<code>) and importing a shared purchase goal."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_verified_game_account_from_session
from app.database import get_db
from app.models import GameAccount
from app.purchase_goals import (
    build_purchase_goals_state,
    import_gear_setup_from_share_payload,
)
from app.sharing import find_valid_share

router = APIRouter()


@router.post("/api/shares/{code}/import")
def import_shared_purchase_goal(
    code: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Imports someone else's shared setup as a new GearSetup of the signed-in
    player (render_purchase_goals_share in app/pages.py); the reverse of POST
    /api/gear-setups/{setup_id}/share. A signed-out visitor is sent to /signup
    by the page script.
    
    content_type="purchase_goal" makes invalid, expired and other-type codes
    404 alike. The response adds importedSetupId, which the share page stores
    under the myscape:purchaseGoals:activeSetupId localStorage key (preferred
    by Purchase Goals' loadState on boot).
    """
    share = find_valid_share(db, code, content_type="purchase_goal")
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    new_setup = import_gear_setup_from_share_payload(db, game_account, share.payload)
    db.commit()
    state = build_purchase_goals_state(db, game_account)
    state["importedSetupId"] = str(new_setup.id)
    return state
