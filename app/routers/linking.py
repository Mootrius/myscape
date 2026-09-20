"""The account-linking flow: website generates a link code, plugin
exchanges it for a long-lived API key. See app/models.py's module
docstring for the full design rationale.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_game_account_from_session, get_current_verified_game_account_from_session
from app.database import get_db
from app.limiter import limiter
from app.models import LINK_CODE_LIFETIME, GameAccount, LinkCode, PlayerApiKey
from app.schemas import LinkExchangeRequest, LinkExchangeResponse, LinkStartResponse
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

    raw_api_key = generate_token()
    api_key = PlayerApiKey(game_account_id=game_account.id, key_hash=hash_token(raw_api_key))
    db.add(api_key)
    db.commit()

    return LinkExchangeResponse(api_key=raw_api_key, player_id=game_account.id)
