"""Goal Tracking endpoints."""
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import goals as goals_module
from app.auth import get_current_verified_game_account_from_session
from app.database import get_db
from app.models import (
    GameAccount,
    Goal,
    SharedContent,
    _utcnow,
)
from app.pages import _SITE_URL
from app.purchase_goals import item_icon_url
from app.schemas import (
    GoalCreateRequest,
    GoalOut,
    GoalReorderRequest,
    GoalsResponse,
    SetGoalSortModeRequest,
)
from app.sharing import SHARE_DEFAULT_LIFETIME, find_valid_share, generate_share_code

router = APIRouter()


def _goal_out(goal: Goal, context: dict) -> GoalOut:
    return GoalOut(
        id=goal.id,
        goal_type=goal.goal_type,
        target_name=goal.target_name,
        metric=goal.metric,
        target_value=goal.target_value,
        current_value=goals_module.current_value(goal, context),
        progress_pct=goals_module.progress_pct(goal, context),
        target_display=goals_module.target_display(goal),
        item_icon=item_icon_url(goal.item_id),
        is_recurring=goal.is_recurring,
        recur_interval=goal.recur_interval,
        recur_unit=goal.recur_unit,
        recur_period_start=goal.recur_period_start,
        baseline_value=goal.baseline_value,
        sort_order=goal.sort_order,
        created_at=goal.created_at,
    )


@router.get("/api/goals", response_model=GoalsResponse)
def list_goals(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Every goal, oldest first, with progress computed live (app/goals.py); Goal
    Tracking's page polls this. Always in created_at order; the client
    re-sorts per sort tab, and sort_mode rides along for the first paint. Also
    where recurring goals roll their period forward
    (maybe_roll_recurring_period); committed once, only if a goal rolled.
    """
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    rolled = False
    for goal in goals:
        if goals_module.maybe_roll_recurring_period(goal, context):
            rolled = True
    if rolled:
        db.commit()
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )


@router.put("/api/goals/sort-mode", response_model=GoalsResponse)
def set_goal_sort_mode(
    payload: SetGoalSortModeRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Switches the active #gtSortTabs button, persisted in
    GameAccount.goal_sort_mode. Leaves Goal.sort_order alone, so "custom"
    replays the last dragged order (see set_goal_order).
    """
    game_account.goal_sort_mode = payload.sort_mode
    db.commit()
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )


@router.put("/api/goals/reorder", response_model=GoalsResponse)
def set_goal_order(
    payload: GoalReorderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a reorder of the goal list in "custom" mode (same rules as
    set_gear_setup_order); also switches to "custom" as a backstop.
    """
    owned_goals = {
        str(g.id): g
        for g in db.query(Goal).filter(Goal.game_account_id == game_account.id).all()
    }
    for index, goal_id in enumerate(payload.order):
        goal = owned_goals.get(goal_id)
        if goal is not None:
            goal.sort_order = float(index)
    game_account.goal_sort_mode = "custom"
    db.commit()
    goals = sorted(owned_goals.values(), key=lambda g: g.created_at)
    context = goals_module.build_progress_context(db, game_account)
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )


@router.post("/api/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Adds one goal. Validation is in app.goals.clean_new_goal and
    clean_target_mode; a GoalValidationError becomes a 400.
    
    A recurring goal's first period starts now, baselined against its current
    absolute_value() so it opens at 0/target_value. payload.recur_start_at
    replaces "now" but is still baselined against the live value (no history
    exists for a past start), so it only phase-locks the period boundaries. A
    one-time GAIN-mode goal gets the same baseline (see Goal.baseline_value).
    """
    try:
        cleaned = goals_module.clean_new_goal(
            payload.goal_type,
            payload.target_name,
            payload.metric,
            payload.target_value,
            payload.item_id,
            payload.is_recurring,
            payload.recur_interval,
            payload.recur_unit,
        )
        target_mode = goals_module.clean_target_mode(
            cleaned["goal_type"], cleaned["metric"], cleaned["is_recurring"], payload.target_mode
        )
    except goals_module.GoalValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    context = goals_module.build_progress_context(db, game_account)
    goal = Goal(game_account_id=game_account.id, **cleaned)
    if goal.is_recurring:
        recur_start_at = payload.recur_start_at
        # Assumed UTC if tz-naive: mixing naive and aware datetimes in
        # maybe_roll_recurring_period (app/goals.py) raises TypeError. The
        # wizard always sends ISO-8601 UTC, so only raw API calls hit this.
        if recur_start_at is not None and recur_start_at.tzinfo is None:
            recur_start_at = recur_start_at.replace(tzinfo=timezone.utc)
        goal.recur_period_start = recur_start_at or _utcnow()
        goal.baseline_value = goals_module.absolute_value(goal, context)
    elif target_mode == "gain":
        goal.baseline_value = goals_module.absolute_value(goal, context)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_out(goal, context)


@router.delete("/api/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    try:
        goal_uuid = uuid.UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    goal = (
        db.query(Goal)
        .filter(Goal.id == goal_uuid, Goal.game_account_id == game_account.id)
        .first()
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    db.delete(goal)
    db.commit()



def build_goal_tracking_share_snapshot(db: Session, game_account: GameAccount) -> dict:
    """Freezes EVERY goal of game_account into the payload POST /api/goals/share
    stores. Frozen as-is, without rolling recurring periods forward as
    list_goals does. model_dump(mode="json") makes uuid/datetime fields plain
    strings so the JSONB payload and its re-import
    (goals_module.import_goals_from_share_payload) round-trip. sortMode rides
    along for the share page.
    """
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    return {
        "goals": [_goal_out(goal, context).model_dump(mode="json") for goal in goals],
        "sortMode": game_account.goal_sort_mode,
    }


@router.post("/api/goals/share")
def create_goal_tracking_share(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes this account's ENTIRE goal list into a SharedContent row and
    returns a myscape.io/s/<code> link; same posture as POST
    /api/mindmaps/{mindmap_id}/share.
    """
    snapshot = build_goal_tracking_share_snapshot(db, game_account)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="goal_tracking",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@router.post("/api/goals/shares/{code}/import")
def import_shared_goals(
    code: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Appends someone else's shared goal list to this player's goals
    (render_goal_tracking_share in app/pages.py); the reverse of POST
    /api/goals/share. GAIN-mode and recurring goals get a fresh baseline
    against THIS account (see goals_module.import_goals_from_share_payload). A
    signed-out visitor is sent to /signup by the page script.
    
    content_type="goal_tracking" makes invalid, expired and other-type codes
    404 alike.
    """
    share = find_valid_share(db, code, content_type="goal_tracking")
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    goals_module.import_goals_from_share_payload(db, game_account, share.payload)
    db.commit()
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )
