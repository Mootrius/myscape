"""Two auth mechanisms for two callers:

- The RuneLite plugin sends the long-lived API key from the link exchange as
`Authorization: Bearer <key>`; it is looked up by SHA-256 hash.
- The website uses a signed session cookie (Starlette SessionMiddleware, wired
in main.py). It is signed, not encrypted, and only holds ids, so nothing
sensitive belongs in it.

"Who is signed in" (an Account) and "which linked character is active" (a
GameAccount) are separate questions (see docs/multi-account-scoping.md):
get_current_account_* for the former (settings, logout, starting a link),
get_current_game_account_* for the latter (virtually every feature endpoint).
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
# Snapshot of Account.token_version at session creation (see app/models.py).
# Lets _load_account_from_session detect sessions invalidated by a password
# change, since there is no server-side session store.
SESSION_TOKEN_VERSION_KEY = "token_version"
# The linked GameAccount this session treats as active (see
# set_active_game_account and _resolve_active_game_account). When absent, the
# first GameAccount is used.
SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY = "active_game_account_id"


def get_current_game_account_from_api_key(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> GameAccount:
    """For the RuneLite plugin: validates the `Authorization: Bearer <api key>`
    header. Always resolves to a linked GameAccount, since a PlayerApiKey is
    only created by a link-code exchange (app/routers/linking.py) that
    attaches to a real GameAccount row.
    """
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
    """Starts the browser session after signup/login. Stamps it with the
    account's current token_version, so the login done by reset_password after
    bumping the version is valid while older sessions stop working.
    
    The active GameAccount is the first one (no switcher UI yet). Signup
    always creates one empty GameAccount (app/routers/auth.py), but an empty
    account.game_accounts is still handled, as in
    _resolve_active_game_account.
    """
    request.session[SESSION_ACCOUNT_ID_KEY] = str(account.id)
    request.session[SESSION_TOKEN_VERSION_KEY] = account.token_version
    if account.game_accounts:
        request.session[SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY] = str(account.game_accounts[0].id)
    else:
        request.session.pop(SESSION_ACTIVE_GAME_ACCOUNT_ID_KEY, None)


def set_active_game_account(request: Request, game_account: GameAccount) -> None:
    """Switches the session's active GameAccount. The caller must first check
    game_account.account_id matches the signed-in Account (see
    get_current_account_from_session); no ownership check here.
    """
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
        log_out_account(request)
        return None

    if request.session.get(SESSION_TOKEN_VERSION_KEY) != account.token_version:
        # Missing key: the session predates token_version (treated as stale,
        # costing one extra login). Mismatch: the password changed and bumped
        # token_version to invalidate old sessions.
        log_out_account(request)
        return None

    return account


def _resolve_active_game_account(request: Request, db: Session, account: Account) -> Optional[GameAccount]:
    """Finds the signed-in Account's active GameAccount. Falls back to the first
    one, persisting that pick into the session, when there is no claim yet or
    the claimed GameAccount no longer belongs to the Account.
    
    Returns None only if the Account has no GameAccount, which signup
    prevents; a row can still be deleted under a live session.
    """
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
    """For endpoints that need only the signed-in Account (settings, logout,
    starting a link, listing/switching characters). 401s if not signed in.
    """
    account = _load_account_from_session(request, db)
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    return account


def get_optional_current_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Account]:
    """For pages that render differently when logged in but do not require it
    (landing nav, 404 page). Never raises.
    """
    return _load_account_from_session(request, db)


def get_current_verified_account_from_session(
    account: Account = Depends(get_current_account_from_session),
) -> Account:
    """get_current_account_from_session plus a 403 if the email is unverified
    (Account.email_verified_at, app/models.py). Used by account-management
    endpoints (change password/email, delete account) that stay reachable
    before game-data features do.
    """
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
    """For endpoints needing game data (bank, dashboard pages, gear setups,
    mindmaps). 401s like get_current_account_from_session; see
    _resolve_active_game_account for why GameAccount resolution essentially
    never fails.
    """
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
    """Optional counterpart of get_current_game_account_from_session, for pages
    where not being signed in is fine.
    """
    if account is None:
        return None
    return _resolve_active_game_account(request, db, account)


def get_current_verified_game_account_from_session(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_verified_account_from_session),
) -> GameAccount:
    """get_current_game_account_from_session plus a verified email requirement.
    Used by virtually every feature endpoint in app/main.py, so an unverified
    account reaches account management but nothing needing game data.
    """
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
    """Identity plus active game data for the server-rendered pages (see
    PlayerView in app/pages/); the page-route counterpart to
    get_optional_current_game_account_from_session. Never raises.
    """
    if account is None:
        return None
    game_account = _resolve_active_game_account(request, db, account)
    return build_player_view(account, game_account)

