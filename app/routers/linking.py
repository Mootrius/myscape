"""The account-linking flow: website generates a link code, plugin
exchanges it for a long-lived API key. See app/models.py's module
docstring for the full design rationale.
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
from app.schemas import GameAccountSummary, LinkExchangeRequest, LinkExchangeResponse, LinkStartResponse
from app.security import generate_token, hash_token

router = APIRouter(prefix="/api", tags=["account-linking"])


def revoke_link(db: Session, game_account: GameAccount) -> None:
    """Clears a linked game account's RuneLite link and revokes every
    currently-active API key on it. Shared by both independent ways a
    link can be undone -- POST /api/link/unlink below (session-
    authenticated, from the website) and POST /api/players/me/unlink in
    main.py (API-key authenticated, from the RuneLite plugin's own
    Unlink button) -- so this is never stuck relying on one of them
    still working. That's not hypothetical: an earlier version of the
    plugin's Unlink button only ever cleared its own locally stored key
    without calling either endpoint, which left a game account's
    account_hash set here with no API key left to call the plugin-side
    endpoint with. The session-authenticated route exists specifically
    as the way out of situations like that one, since it needs nothing
    from the plugin at all."""
    now = datetime.now(timezone.utc)
    for api_key in game_account.api_keys:
        if api_key.is_active:
            api_key.revoked_at = now
    game_account.account_hash = None
    game_account.runescape_name = None
    # Friendships are with the *character*, and this slot can be
    # relinked to a different OSRS character afterward -- so every
    # friend and pending request goes with the link.
    db.query(Friendship).filter(
        (Friendship.requester_id == game_account.id) | (Friendship.addressee_id == game_account.id)
    ).delete(synchronize_session=False)
    db.commit()


@router.post("/link/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_via_session(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_session),
):
    """Lets a signed-in player unlink their active game account straight
    from the website (see the "Unlink" button next to the "Linked to
    <name>" note on /dashboard in app/pages.py), using only their
    browser session -- no working plugin API key required. See
    revoke_link() above for why this exists as a second, independent
    path."""
    revoke_link(db, game_account)


@router.post("/link/start", response_model=LinkStartResponse)
def start_link(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Called by the website for the signed-in player's active game
    account (via their session cookie -- see app/routers/auth.py).
    Generates a link code, shows it to them exactly once (this
    response), and stores only its hash."""
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
    """Called by the RuneLite plugin, exactly once per link code. Trades
    the short-lived code for a long-lived API key and binds the linked
    game account to its stable account_hash. Rate-limited per-IP
    separately from the rest of the API, since this is the one endpoint
    where a caller benefits from guessing -- 10 attempts/minute makes
    brute-forcing a 24-byte random code (192 bits of entropy)
    astronomically infeasible long before rate-limiting is even the
    binding constraint, while still allowing normal retries after a
    typo.

    The response's `player_id` field is deliberately unchanged in name
    and meaning (an opaque id the plugin stores) even though it's now a
    GameAccount id rather than a Player id -- the plugin needs zero
    code changes for multi-account support (see
    docs/multi-account-scoping.md), which only holds if this wire
    format stays exactly as it was."""
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
    # Every linked character gets a code right away (private profile by
    # default, so nothing is exposed) -- it doubles as the friend code.
    if not game_account.public_code:
        game_account.public_code = generate_public_code(db)

    raw_api_key = generate_token()
    api_key = PlayerApiKey(game_account_id=game_account.id, key_hash=hash_token(raw_api_key))
    db.add(api_key)
    db.commit()

    # Seeds Goal Tracking's KC column with this character's real
    # lifetime totals right as the link is established -- see
    # app/hiscores.py's own top-of-file comment for the full design:
    # this is now the ONLY place a hiscores pull fires on a first-time
    # link (a re-link through this same endpoint gets the same
    # treatment for free, re-anchoring to the real hiscores number
    # rather than trusting whatever chat-parsed data happened to be on
    # file from before the account was unlinked). Best-effort and
    # non-blocking: a Jagex hiccup (or this account simply not being
    # rankable yet) here should never fail the link itself -- the
    # plugin still gets its API key either way, and the manual
    # /api/players/me/hiscores/sync endpoint (or the player's next
    # relink) can seed the baseline later.
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
    """Every OSRS character linked (or slotted but not yet linked --
    see add_game_account below) under the signed-in Account, oldest
    first, for the account page's Linked Accounts list (step 7 of
    docs/multi-account-scoping.md). Uses the *optional* active-game-
    account dependency, not the required one every real feature
    endpoint uses -- this page needs to render even for the (now
    reachable, via delete_game_account below) zero-GameAccounts case,
    not 409 outright."""
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
    """Creates a new, empty, unlinked GameAccount under the signed-in
    Account and makes it the session's active one -- the entry point
    for linking a second (or third, ...) OSRS character. No cap (see
    docs/multi-account-scoping.md's Decisions) -- the account page's
    own "Add another account" button is what calls this.

    Requires a verified email, the same bar start_link itself already
    gates on -- there'd be nothing useful to do with a fresh slot
    otherwise. Deliberately does nothing beyond create-and-activate:
    the account page just reloads after this succeeds, and the
    existing link banner (see _link_banner in app/pages.py) takes it
    from there exactly as it would for a brand new signup's first
    link, since this new slot's account_hash is NULL the same way."""
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
    """Switches which of the signed-in Account's linked GameAccounts
    this session treats as active -- the account page's own "Switch"
    button. Base (unverified-allowed) dependency, same reasoning as
    unlink_via_session above: this is account management, not a
    feature that touches game data itself."""
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
    """Permanently deletes this linked character and every row of game
    data attached to it -- bank, gear setups, mindmaps, loot history,
    everything (see GameAccount's own cascade="all, delete-orphan"
    relationships in app/models.py). NOT the same action as Unlink
    above, which only disconnects the RuneLite plugin and revokes its
    API keys while keeping the GameAccount row and its data intact for
    a later re-link -- this is the account page's "Remove" button, and
    it does not come back.

    Per docs/multi-account-scoping.md's Decisions there's no minimum:
    deleting the Account's only remaining GameAccount is allowed and
    leaves it with zero, the same state a brand new signup is in
    before its first link -- see get_optional_current_game_account_from_session
    and list_game_accounts above for how the rest of the app already
    handles that. If the deleted GameAccount happened to be this
    session's active one, the next request that needs one just falls
    back to whatever's left (see _resolve_active_game_account in
    app/auth.py) -- nothing here needs to touch the session directly."""
    game_account = (
        db.query(GameAccount)
        .filter(GameAccount.id == game_account_id, GameAccount.account_id == account.id)
        .first()
    )
    if game_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game account not found.")
    db.delete(game_account)
    db.commit()
