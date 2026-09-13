"""Two separate auth mechanisms, for two separate callers:

- The RuneLite plugin authenticates with the long-lived API key it got
  from the account-linking exchange, sent as a standard
  `Authorization: Bearer <key>` header on every request.
- The website authenticates a browser with a signed session cookie
  (Starlette's SessionMiddleware, wired up in main.py) set at login.

Neither one ever compares a raw secret directly -- the API key is
looked up by its SHA-256 hash, and the session cookie only ever holds a
player id (it's signed, not encrypted, so nothing sensitive belongs in
it).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, PlayerApiKey
from app.security import hash_token

SESSION_PLAYER_ID_KEY = "player_id"


def get_current_player_from_api_key(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Player:
    """For the RuneLite plugin: validates the `Authorization: Bearer
    <api key>` header set during account linking."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header (expected 'Bearer <api key>').",
        )
    raw_key = authorization[len("bearer "):].strip()
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty API key.")

    key_hash = hash_token(raw_key)
    api_key = (
        db.query(PlayerApiKey)
        .filter(PlayerApiKey.key_hash == key_hash, PlayerApiKey.revoked_at.is_(None))
        .first()
    )
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key.")

    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return api_key.player


def log_in_player(request: Request, player: Player) -> None:
    """Call after a successful signup/login to start the browser session."""
    request.session[SESSION_PLAYER_ID_KEY] = str(player.id)


def log_out_player(request: Request) -> None:
    request.session.pop(SESSION_PLAYER_ID_KEY, None)


def _load_player_from_session(request: Request, db: Session) -> Optional[Player]:
    raw_player_id = request.session.get(SESSION_PLAYER_ID_KEY)
    if not raw_player_id:
        return None

    try:
        player_id = uuid.UUID(raw_player_id)
    except ValueError:
        log_out_player(request)
        return None

    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None:
        # The player row was deleted after the session cookie was issued.
        log_out_player(request)
        return None

    return player


def get_current_player_from_session(
    request: Request,
    db: Session = Depends(get_db),
) -> Player:
    """For endpoints that require an active logged-in session, set by
    /api/auth/login or /api/auth/signup. 401s if there isn't one."""
    player = _load_player_from_session(request, db)
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    return player


def get_optional_current_player_from_session(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Player]:
    """For pages that render differently when logged in but don't
    require it (the landing page's nav, mainly) -- never raises."""
    return _load_player_from_session(request, db)
