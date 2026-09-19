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
# Snapshot of Player.token_version at the moment this session was
# created (see that column's own docstring in app/models.py) -- lets
# _load_player_from_session below detect a session that's been
# invalidated by a password reset elsewhere, since there's no
# server-side session store to delete rows from otherwise.
SESSION_TOKEN_VERSION_KEY = "token_version"


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
    """Call after a successful signup/login to start the browser
    session. Also stamps the session with the player's *current*
    token_version -- for a fresh signup/login that's just whatever it
    already was, but for the login reset_password does on your behalf
    right after changing a password, this is what makes the new
    session valid under the just-bumped version while every other
    session (still carrying the old version) stops working."""
    request.session[SESSION_PLAYER_ID_KEY] = str(player.id)
    request.session[SESSION_TOKEN_VERSION_KEY] = player.token_version


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

    if request.session.get(SESSION_TOKEN_VERSION_KEY) != player.token_version:
        # Either this session predates token_version existing at all
        # (missing key -- treated as stale rather than grandfathered
        # in, so this only ever costs each browser one extra login),
        # or the player reset their password since this cookie was
        # issued and reset_password bumped token_version specifically
        # to invalidate sessions like this one.
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


def get_current_verified_player_from_session(player: Player = Depends(get_current_player_from_session)) -> Player:
    """Same as get_current_player_from_session, plus 403s if the
    player's email hasn't been confirmed yet (see
    Player.email_verified_at's own docstring in app/models.py). This is
    the dependency virtually every real feature endpoint in app/main.py
    uses -- bank/inventory/etc. data, the dashboard pages, starting a
    plugin link -- so a not-yet-verified player can log in and reach
    account-management (this endpoint itself, logging out, resending
    the verification email, unlinking) but nothing else, until they
    click the link in their confirmation email. Account management
    stays on the plain get_current_player_from_session above
    specifically because verifying (and asking for a fresh link) has to
    stay reachable *before* verification, or an unverified player would
    have no way to ever get unstuck."""
    if not player.email_verified_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before continuing.",
        )
    return player
