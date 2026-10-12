"""The account-linking flow: the website generates a link code and the plugin
exchanges it for a long-lived API key. See the module docstring in
app/models.py for the design.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import hiscores as sync_hiscores_module
from app.auth import (
    get_current_account_from_session,
    get_current_game_account_from_session,
    get_current_verified_account_from_session,
    get_current_verified_game_account_from_session,
    get_optional_current_game_account_from_session,
    set_active_game_account,
)
from app.database import get_db
from app.limiter import limiter
from app.models import LINK_CODE_LIFETIME, Account, Friendship, GameAccount, LinkCode, PlayerApiKey
from app.public_profile import generate_public_code
from app.schemas import (
    GameAccountSummary,
    LinkExchangeRequest,
    LinkExchangeResponse,
    LinkStartResponse,
)
from app.security import generate_token, hash_token

router = APIRouter(prefix="/api", tags=["account-linking"])


def revoke_link(db: Session, game_account: GameAccount) -> None:
    """Clears a game account's RuneLite link and revokes its active API keys.
    Shared by POST /api/link/unlink below (session-authenticated, from the
    website) and POST /api/players/me/unlink in main.py (API-key
    authenticated, from the plugin), so a link can always be undone even if
    one path is unusable, e.g. the plugin discarded its key without calling
    either.
    """
    now = datetime.now(timezone.utc)
    for api_key in game_account.api_keys:
        if api_key.is_active:
            api_key.revoked_at = now
    game_account.account_hash = None
    game_account.runescape_name = None
    # Friendships belong to the *character*, and the slot can be relinked to a
    # different one, so friends and pending requests go with the link.
    db.query(Friendship).filter(
        (Friendship.requester_id == game_account.id) | (Friendship.addressee_id == game_account.id)
    ).delete(synchronize_session=False)
    db.commit()


@router.post("/link/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_via_session(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_session),
):
    """Unlinks the active game account from the website using only the browser
    session (the "Unlink" button on /dashboard in app/pages/). See
    revoke_link() for why this second path exists.
    """
    revoke_link(db, game_account)


@router.post("/link/start", response_model=LinkStartResponse)
def start_link(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Called by the website for the signed-in player's active game account.
    Generates a link code, shows it once in this response, and stores only its
    hash.
    """
    raw_code = generate_token()
    expires_at = datetime.now(timezone.utc) + LINK_CODE_LIFETIME
    link_code = LinkCode(game_account_id=game_account.id, code_hash=hash_token(raw_code), expires_at=expires_at)
    db.add(link_code)
    db.commit()

    return LinkStartResponse(code=raw_code, expires_at=expires_at)


@router.post("/link/exchange", response_model=LinkExchangeResponse)
@limiter.limit("10/minute")
def exchange_link_code(
    request: Request,  # required by slowapi to key the rate limit off the caller's IP
    payload: LinkExchangeRequest,
    db: Session = Depends(get_db),
):
    """Called by the plugin, once per link code: trades the short-lived code for
    a long-lived API key and binds the game account to its stable
    account_hash. Rate-limited per IP separately from the rest of the API
    because this is the one endpoint where guessing pays; 10 attempts/minute
    is infeasible against a 24-byte (192-bit) code while allowing retries
    after a typo.
    
    The response's `player_id` keeps its name and meaning (an opaque id)
    although it is now a GameAccount id, so the plugin needs no changes for
    multi-account support (docs/multi-account-scoping.md). The wire format
    must stay as is.
    """
    code_hash = hash_token(payload.code)
    link_code = db.query(LinkCode).filter(LinkCode.code_hash == code_hash).first()
    if link_code is None or not link_code.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link code.")

    other_game_account = (
        db.query(GameAccount)
        .filter(GameAccount.account_hash == payload.account_hash, GameAccount.id != link_code.game_account_id)
        .first()
    )
    if other_game_account is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This game account is already linked to a different myscape account.",
        )

    link_code.used_at = datetime.now(timezone.utc)

    game_account = link_code.game_account
    game_account.account_hash = payload.account_hash
    if payload.runescape_name:
        game_account.runescape_name = payload.runescape_name
    # Every linked character gets a code right away (private profile by default,
    # so nothing is exposed); it doubles as the friend code.
    if not game_account.public_code:
        game_account.public_code = generate_public_code(db)

    raw_api_key = generate_token()
    api_key = PlayerApiKey(game_account_id=game_account.id, key_hash=hash_token(raw_api_key))
    db.add(api_key)
    db.commit()

    # Seeds the KC column with the character's lifetime hiscores totals (see
    # app/hiscores.py). A re-link re-anchors to the hiscores rather than
    # trusting older chat-parsed data. Best-effort: a Jagex failure must not
    # fail the link; the manual /api/players/me/hiscores/sync endpoint or the
    # next relink can seed it later.
    try:
        sync_hiscores_module.sync_hiscores(db, game_account)
    except sync_hiscores_module.HiscoresSyncError:
        pass

    return LinkExchangeResponse(api_key=raw_api_key, player_id=game_account.id)


@router.get("/link/game-accounts", response_model=List[GameAccountSummary])
def list_game_accounts(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
    active_game_account: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    """Every linked (or slotted but unlinked) OSRS character under the signed-in
    Account, oldest first, for the account page's Linked Accounts list. Uses
    the *optional* active-game-account dependency so the page renders in the
    zero-GameAccounts case instead of 409ing.
    """
    game_accounts = (
        db.query(GameAccount)
        .filter(GameAccount.account_id == account.id)
        .order_by(GameAccount.created_at)
        .all()
    )
    active_id = active_game_account.id if active_game_account else None
    return [
        GameAccountSummary(
            id=game_account.id,
            runescape_name=game_account.runescape_name,
            linked=game_account.account_hash is not None,
            active=(game_account.id == active_id),
        )
        for game_account in game_accounts
    ]


@router.post("/link/game-accounts", response_model=GameAccountSummary, status_code=status.HTTP_201_CREATED)
def add_game_account(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_verified_account_from_session),
):
    """Creates an empty, unlinked GameAccount under the signed-in Account and
    makes it the session's active one: the entry point for linking another
    character (no cap; see docs/multi-account-scoping.md). Requires a verified
    email, like start_link. The account page reloads afterwards and the link
    banner (_link_banner in app/pages/) takes over, since account_hash is
    NULL.
    """
    game_account = GameAccount(account_id=account.id)
    db.add(game_account)
    db.commit()
    db.refresh(game_account)
    set_active_game_account(request, game_account)
    return GameAccountSummary(id=game_account.id, runescape_name=None, linked=False, active=True)


@router.post("/link/game-accounts/{game_account_id}/activate", status_code=status.HTTP_204_NO_CONTENT)
def activate_game_account(
    game_account_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Switches the session's active GameAccount (the account page's "Switch"
    button). Uses the unverified-allowed dependency, as in unlink_via_session:
    this is account management.
    """
    game_account = (
        db.query(GameAccount)
        .filter(GameAccount.id == game_account_id, GameAccount.account_id == account.id)
        .first()
    )
    if game_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game account not found.")
    set_active_game_account(request, game_account)


@router.delete("/link/game-accounts/{game_account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game_account(
    game_account_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Permanently deletes this linked character and all its game data (bank,
    gear setups, mindmaps, loot history; GameAccount's cascade="all,
    delete-orphan" in app/models.py). Unlike Unlink, which keeps the row and
    data for a later re-link, this is the account page's "Remove" button and
    is irreversible.
    
    There is no minimum: removing the last GameAccount is allowed and leaves
    the same state as a new signup (see list_game_accounts above). If it was
    the session's active one, _resolve_active_game_account (app/auth.py) falls
    back on the next request.
    """
    game_account = (
        db.query(GameAccount)
        .filter(GameAccount.id == game_account_id, GameAccount.account_id == account.id)
        .first()
    )
    if game_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game account not found.")
    db.delete(game_account)
    db.commit()
