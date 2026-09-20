"""Two separate auth mechanisms, for two separate callers:

- The RuneLite plugin authenticates with the long-lived API key it got
  from the account-linking exchange, sent as a standard
  `Authorization: Bearer <key>` header on every request.
- The website authenticates a browser with a signed session cookie
  (Starlette's SessionMiddleware, wired up in main.py) set at login.

Neither one ever compares a raw secret directly -- the API key is
looked up by its SHA-256 hash, and the session cookie only ever holds
an account id (it's signed, not encrypted, so nothing sensitive
belongs in it).

Since the multi-account split (see docs/multi-account-scoping.md),
"who's signed in" (an Account) and "which linked OSRS character is
active right now" (a GameAccount) are two different questions with two
different dependency families below -- get_current_account_* for the
former, get_current_game_account_* for the latter. Account management
(settings, logging out, starting a link) wants the Account; virtually
every real feature endpoint (bank data, skills, gear setups, ...)
wants the active GameAccount instead.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, GameAccount, PlayerApiKey
from app.pages import PlayerView, build_player_view
from app.security import hash_token

SESSION_ACCOUNT_ID_KEY = "account_id"
# Snapshot of Account.token_version at the moment this session was
# created (see that column's own docstring in app/models.py) -- lets
# _load_account_from_session below detect a session that's been
# invalidated by a password reset elsewhere, since there's no
# server-side session store to delete rows from otherwise.
SESSION_TOKEN_VERSION_KEY = "token_version"
# Which of the signed-in Account's linked GameAccounts this session
# currently treats as "active" -- see set_active_game_account and
# _resolve_active_game_account below. Absent for a session predating
# multi-account support entirely; falls back to whichever GameAccount
# comes first in that case, same as a fresh login does.
SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY = "active_game_account_id"


def get_current_game_account_from_api_key(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> GameAccount:
    """For the RuneLite plugin: validates the `Authorization: Bearer
    <api key>` header set during account linking. Always resolves to a
    real, already-linked GameAccount -- a PlayerApiKey only ever gets
    created by a successful link-code exchange (see
    app/routers/linking.py), which always has a real GameAccount row
    to attach to by construction, so there's no "not linked yet" gap
    to handle here the way there is on the session side below."""
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

    return api_key.game_account


def log_in_account(request: Request, account: Account) -> None:
    """Call after a successful signup/login to start the browser
    session. Also stamps the session with the account's *current*
    token_version -- for a fresh signup/login that's just whatever it
    already was, but for the login reset_password does on your behalf
    right after changing a password, this is what makes the new
    session valid under the just-bumped version while every other
    session (still carrying the old version) stops working.

    Also picks which linked GameAccount is "active" for this session:
    whichever one comes first, since there's no switcher UI yet (see
    docs/multi-account-scoping.md's step 7). Signup always creates one
    empty GameAccount alongside the Account itself (see
    app/routers/auth.py's signup endpoint), so there's always at least
    one to pick here, linked or not -- account.game_accounts empty is
    kept as a real (if normally unreachable) case anyway, the same way
    _resolve_active_game_account below does."""
    request.session[SESSION_ACCOUNT_ID_KEY] = str(account.id)
    request.session[SESSION_TOKEN_VERSION_KEY] = account.token_version
    if account.game_accounts:
        request.session[SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY] = str(account.game_accounts[0].id)
    else:
        request.session.pop(SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY, None)


def set_active_game_account(request: Request, game_account: GameAccount) -> None:
    """Switches which linked GameAccount this session treats as active.
    The caller is responsible for checking game_account.account_id
    actually matches the signed-in Account first (see
    get_current_account_from_session) -- this itself does no ownership
    check, same division of responsibility as log_in_account above."""
    request.session[SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY] = str(game_account.id)


def log_out_account(request: Request) -> None:
    request.session.pop(SESSION_ACCOUNT_ID_KEY, None)
    request.session.pop(SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY, None)


def _load_account_from_session(request: Request, db: Session) -> Optional[Account]:
    raw_account_id = request.session.get(SESSION_ACCOUNT_ID_KEY)
    if not raw_account_id:
        return None

    try:
        account_id = uuid.UUID(raw_account_id)
    except ValueError:
        log_out_account(request)
        return None

    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        # The account row was deleted after the session cookie was issued.
        log_out_account(request)
        return None

    if request.session.get(SESSION_TOKEN_VERSION_KEY) != account.token_version:
        # Either this session predates token_version existing at all
        # (missing key -- treated as stale rather than grandfathered
        # in, so this only ever costs each browser one extra login),
        # or the account reset their password since this cookie was
        # issued and reset_password bumped token_version specifically
        # to invalidate sessions like this one.
        log_out_account(request)
        return None

    return account


def _resolve_active_game_account(request: Request, db: Session, account: Account) -> Optional[GameAccount]:
    """Given an already-resolved, signed-in Account, finds whichever of
    its linked GameAccounts this session currently treats as active.
    Falls back to whichever GameAccount comes first -- and persists
    that pick into the session -- if there's no active-game-account
    claim yet (a session from before multi-account support), or if the
    claim doesn't actually belong to this Account anymore (stale after
    that GameAccount was removed).

    Returns None only if the Account has no linked GameAccount at all
    to fall back to, which never happens in practice once signup
    creates one empty GameAccount alongside every new Account (see
    app/routers/auth.py) -- kept as a real return type rather than
    assumed away, since a row can still be deleted out from under a
    live session the same way _load_account_from_session already
    accounts for above."""
    raw_game_account_id = request.session.get(SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY)
    game_account = None
    if raw_game_account_id:
        try:
            game_account_id = uuid.UUID(raw_game_account_id)
        except ValueError:
            game_account_id = None
        if game_account_id is not None:
            game_account = (
                db.query(GameAccount)
                .filter(GameAccount.id == game_account_id, GameAccount.account_id == account.id)
                .first()
            )

    if game_account is None:
        game_account = (
            db.query(GameAccount)
            .filter(GameAccount.account_id == account.id)
            .order_by(GameAccount.created_at)
            .first()
        )
        if game_account is not None:
            request.session[SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY] = str(game_account.id)

    return game_account


def get_current_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
) -> Account:
    """For endpoints that only need to know who's signed in, not which
    linked character is active right now -- account settings, logging
    out, starting a link, listing/switching linked characters. 401s if
    there isn't a signed-in Account."""
    account = _load_account_from_session(request, db)
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    return account


def get_optional_current_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Account]:
    """For pages that render differently when logged in but don't
    require it (the landing page's nav, the 404 page's home-teleport
    link, mainly) -- never raises."""
    return _load_account_from_session(request, db)


def get_current_verified_account_from_session(
    account: Account = Depends(get_current_account_from_session),
) -> Account:
    """Same as get_current_account_from_session, plus 403s if the
    account's email hasn't been confirmed yet (see
    Account.email_verified_at's own docstring in app/models.py). Used
    by account-management endpoints that should stay reachable before
    a game-data feature does -- changing password/email, deleting the
    account -- but not by anything that needs actual game data, which
    goes through get_current_verified_game_account_from_session below
    instead."""
    if not account.email_verified_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before continuing.",
        )
    return account


def get_current_game_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
) -> GameAccount:
    """For endpoints that need actual game data (bank/inventory/etc.,
    the dashboard's item-backed pages, gear setups, mindmaps, ...) --
    the direct replacement for the old, single
    get_current_player_from_session, now split from
    get_current_account_from_session above since "who's signed in" and
    "which linked character is active" are different questions
    post-multi-account. 401s under the same conditions
    get_current_account_from_session would (not signed in, stale
    session); see _resolve_active_game_account's own docstring for why
    GameAccount resolution itself essentially never fails on its own."""
    game_account = _resolve_active_game_account(request, db, account)
    if game_account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No linked game account found for this session.",
        )
    return game_account


def get_optional_current_game_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
    account: Optional[Account] = Depends(get_optional_current_account_from_session),
) -> Optional[GameAccount]:
    """Optional-Account counterpart to get_current_game_account_from_session
    above, for the same not-signed-in-is-fine pages that
    get_optional_current_account_from_session serves."""
    if account is None:
        return None
    return _resolve_active_game_account(request, db, account)


def get_current_verified_game_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_verified_account_from_session),
) -> GameAccount:
    """Same as get_current_game_account_from_session, plus requires the
    signed-in Account's email to already be verified (see
    get_current_verified_account_from_session above). This is the
    dependency virtually every real feature endpoint in app/main.py
    uses -- bank/inventory/etc. data, the dashboard pages -- so a
    not-yet-verified account can log in and reach account-management
    (get_current_verified_account_from_session's own endpoints) but
    nothing that needs game data, until they click the link in their
    confirmation email."""
    game_account = _resolve_active_game_account(request, db, account)
    if game_account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No linked game account found for this session.",
        )
    return game_account

def get_optional_current_player_view_from_session(
    request: Request,
    db: Session = Depends(get_db),
    account: Optional[Account] = Depends(get_optional_current_account_from_session),
) -> Optional[PlayerView]:
    """Combined identity + active-game-data view for the website's own
    server-rendered pages (see PlayerView's own docstring in
    app/pages.py for why those pages need both at once) -- the page-
    route counterpart to get_optional_current_game_account_from_session
    above, which serves the website's own JSON-data endpoints instead.
    Never raises, same as that one and as
    get_optional_current_account_from_session itself."""
    if account is None:
        return None
    game_account = _resolve_active_game_account(request, db, account)
    return build_player_view(account, game_account)

