"""Character Overview data, public profiles (/c/<code> and /api/public/*) and profile settings."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import (
    get_current_verified_game_account_from_session,
    get_optional_current_game_account_from_session,
    get_optional_current_player_view_from_session,
)
from app.database import get_db
from app.limiter import limiter
from app.models import (
    GameAccount,
    PermanentExample,
    _utcnow,
)
from app.pages import (
    _MODEL_VIEWER_BACKGROUNDS,
    _SITE_URL,
    PlayerView,
    render_goal_tracking_share,
    render_loot_tracker_share,
    render_mindmap_share,
    render_public_character_overview,
    render_purchase_goals_share,
    render_storages_share,
)
from app.permanent_examples import (
    find_permanent_profile,
    frozen_owner,
)
from app.public_profile import (
    find_viewable_game_account,
    format_cooldown_remaining,
    generate_public_code,
    regenerate_cooldown_remaining,
)
from app.routers.shared import (
    _character_overview_progress_payload,
    _character_overview_summary_payload,
    _collection_log_payload,
    _skills_payload,
)
from app.schemas import (
    ModelViewerBackgroundUpdateRequest,
    PublicProfileUpdateRequest,
)
from app.sharing import find_valid_share

router = APIRouter()


@router.get("/api/character-overview/summary")
def character_overview_summary(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Character Overview's summary row (session-authenticated). Null stats
    render as an em dash (render_character_overview in app/pages/).
    """
    return _character_overview_summary_payload(game_account)


@router.get("/api/character-overview/progress")
def character_overview_progress(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Session-authenticated wrapper around _character_overview_progress_payload."""
    return _character_overview_progress_payload(game_account)


def _character_overview_model_response(game_account: GameAccount) -> Response:
    """The .glb response, shared by the session-scoped and public endpoints."""
    if not game_account.character_model_glb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No character model captured yet.")
    return Response(
        content=game_account.character_model_glb,
        media_type="model/gltf-binary",
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )


@router.get("/api/character-overview/model")
def character_overview_model(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Character Overview's 3D-viewer payload (session-authenticated): raw .glb
    bytes (model/gltf-binary) for three.js GLTFLoader#parse. 404, not an empty
    200, when nothing is captured.
    """
    return _character_overview_model_response(game_account)


def _public_profile_payload(game_account: GameAccount) -> dict:
    """The is_public/code/url trio returned by read/update_public_profile and
    regenerate_public_profile_code.
    """
    return {
        "isPublic": game_account.is_public_profile,
        "code": game_account.public_code,
        "url": f"{_SITE_URL}/c/{game_account.public_code}" if game_account.public_code else None,
    }


@router.get("/api/players/me/public-profile")
def read_public_profile(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The settings card's initial-state read (session-authenticated)."""
    return _public_profile_payload(game_account)


@router.post("/api/players/me/public-profile")
def update_public_profile(
    payload: PublicProfileUpdateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Flips GameAccount.is_public_profile. A code is generated the first time a
    character goes public and kept afterwards, so re-publishing reuses the
    link.
    """
    game_account.is_public_profile = payload.is_public
    if payload.is_public and not game_account.public_code:
        game_account.public_code = generate_public_code(db)
        game_account.public_code_regenerated_at = _utcnow()
    db.commit()
    return _public_profile_payload(game_account)


@router.post("/api/players/me/public-profile/regenerate-code")
def regenerate_public_profile_code(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Issues a fresh code, abandoning the old one. Throttled to once per day
    (PUBLIC_CODE_REGENERATE_COOLDOWN in app/public_profile.py) with a 429.
    """
    remaining = regenerate_cooldown_remaining(game_account)
    if remaining is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You can generate a new link again in about {format_cooldown_remaining(remaining)}.",
        )
    game_account.public_code = generate_public_code(db)
    game_account.public_code_regenerated_at = _utcnow()
    db.commit()
    return _public_profile_payload(game_account)


@router.post("/api/players/me/model-viewer-background")
def update_model_viewer_background(
    payload: ModelViewerBackgroundUpdateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Called by the shuffle button (shuffleBackground in app/pages/),
    fire-and-forget. The schema checks index >= 0; the upper bound is
    _MODEL_VIEWER_BACKGROUNDS' length in app/pages/.
    """
    if payload.index >= len(_MODEL_VIEWER_BACKGROUNDS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"index must be less than {len(_MODEL_VIEWER_BACKGROUNDS)}.",
        )
    game_account.model_viewer_background_index = payload.index
    db.commit()
    return {"index": game_account.model_viewer_background_index}


# Public, unauthenticated reads for myscape.io/c/<code>
#
# Each mirrors a session-authenticated endpoint with the same payload builder,
# resolving by public_code. A missing code and a private profile 404 identically.
# Rate-limited per IP to bound enumeration of the ~28.6 million possible codes.
def _find_viewable_or_frozen(db: Session, code: str, viewer: Optional[GameAccount] = None):
    """404s unless the profile is public, or the session's active character
    (`viewer`) is its owner or an accepted friend (find_viewable_game_account).
    A non-viewable code that is a permanent example (app/permanent_examples.py)
    returns its frozen PermanentExample instead.
    """
    game_account = find_viewable_game_account(db, code, viewer)
    if game_account is not None:
        return game_account
    frozen = find_permanent_profile(db, code)
    if frozen is not None:
        return frozen
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")


@router.get("/api/public/{code}/summary")
@limiter.limit("30/minute")
def public_character_overview_summary(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["summary"]
    return _character_overview_summary_payload(game_account)


@router.get("/api/public/{code}/progress")
@limiter.limit("30/minute")
def public_character_overview_progress(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["progress"]
    return _character_overview_progress_payload(game_account)


@router.get("/api/public/{code}/skills")
@limiter.limit("30/minute")
def public_skills(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["skills"]
    return _skills_payload(game_account)


@router.get("/api/public/{code}/collection-log")
@limiter.limit("30/minute")
def public_collection_log(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["collection-log"]
    return _collection_log_payload(game_account)


@router.get("/api/public/{code}/model")
@limiter.limit("30/minute")
def public_character_overview_model(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        if not game_account.model_glb:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No character model captured yet.")
        return Response(
            content=game_account.model_glb,
            media_type="model/gltf-binary",
            headers={"Cache-Control": "private, max-age=0, must-revalidate"},
        )
    return _character_overview_model_response(game_account)


@router.get("/c/{code}", response_class=HTMLResponse)
@limiter.limit("30/minute")
def public_character_overview_page(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session),
    viewer_game_account: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    """The shared-link page: render_public_character_overview (app/pages/)
    wired to the public endpoints above. Missing and private codes 404 into
    the styled not-found page.
    """
    # Friends and the owner can open a private profile too
    # (find_viewable_game_account).
    game_account = find_viewable_game_account(db, code, viewer_game_account)
    if game_account is None:
        # A README permanent example renders from its frozen copy; the page's
        # fetches are answered the same way by /api/public/<code>/*.
        frozen = find_permanent_profile(db, code)
        if frozen is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return render_public_character_overview(frozen_owner(frozen.owner_name, frozen.code), viewer)
    return render_public_character_overview(game_account, viewer)


@router.get("/s/{code}", response_class=HTMLResponse)
@limiter.limit("30/minute")
def shared_content_page(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session),
):
    """Landing spot for every myscape.io/s/<code>: looks the code up once and
    dispatches on content_type to a render_*_share function. Missing and
    expired codes 404 identically (see find_valid_share in app/sharing.py).
    """
    share = find_valid_share(db, code)
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    # The share's owner, queried by FK (app/pages/ stays DB-free). May be None if
    # the account was deleted (no cascade on this FK); render_loot_tracker_share
    # handles that.
    if share.game_account_id is None:
        # A permanent example's frozen copy carries its owner's name alongside
        # the payload.
        owner = frozen_owner(getattr(share, "frozen_owner_name", None))
    else:
        owner = db.query(GameAccount).filter(GameAccount.id == share.game_account_id).first()
    if share.content_type == "loot_tracker":
        return render_loot_tracker_share(share, owner, viewer)
    if share.content_type == "purchase_goal":
        return render_purchase_goals_share(share, owner, viewer)
    if share.content_type == "possessions":
        return render_storages_share(share, owner, viewer)
    if share.content_type == "mindmap":
        return render_mindmap_share(share, owner, viewer)
    if share.content_type == "goal_tracking":
        return render_goal_tracking_share(share, owner, viewer)
    # Unreachable: content_type is only set by this file's create-share
    # endpoints. Fail loudly rather than guess.
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
