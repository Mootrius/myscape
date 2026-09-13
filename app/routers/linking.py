"""The account-linking flow: website generates a link code, plugin
exchanges it for a long-lived API key. See app/models.py's module
docstring for the full design rationale.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import LINK_CODE_LIFETIME, LinkCode, Player, PlayerApiKey
from app.schemas import (
    LinkExchangeRequest,
    LinkExchangeResponse,
    LinkStartRequest,
    LinkStartResponse,
    PlayerCreate,
    PlayerOut,
)
from app.security import generate_token, hash_token

router = APIRouter(prefix="/api", tags=["account-linking"])


@router.post("/players", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
def create_player(payload: PlayerCreate, db: Session = Depends(get_db)):
    """Stand-in for real signup until the website has an actual
    login flow (see README "Next steps"). Gets-or-creates a Player row
    by email so the rest of the linking flow has something to test
    against; this endpoint should be replaced -- not built on top of --
    once real authenticated sessions exist, since right now anyone who
    knows an email can act as that player."""
    existing = db.query(Player).filter(Player.email == payload.email).first()
    if existing:
        return existing
    player = Player(email=payload.email)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


@router.post("/link/start", response_model=LinkStartResponse)
def start_link(payload: LinkStartRequest, db: Session = Depends(get_db)):
    """Called by the website for a signed-in player. Generates a link
    code, shows it to them exactly once (this response), and stores only
    its hash. TODO once real sessions exist: take the player from the
    authenticated session instead of a client-supplied player_id."""
    player = db.query(Player).filter(Player.id == payload.player_id).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such player.")

    raw_code = generate_token()
    expires_at = datetime.now(timezone.utc) + LINK_CODE_LIFETIME
    link_code = LinkCode(player_id=player.id, code_hash=hash_token(raw_code), expires_at=expires_at)
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
    the short-lived code for a long-lived API key and binds the player
    to their stable account_hash. Rate-limited per-IP separately from
    the rest of the API, since this is the one endpoint where a caller
    benefits from guessing -- 10 attempts/minute makes brute-forcing a
    24-byte random code (192 bits of entropy) astronomically infeasible
    long before rate-limiting is even the binding constraint, while
    still allowing normal retries after a typo."""
    code_hash = hash_token(payload.code)
    link_code = db.query(LinkCode).filter(LinkCode.code_hash == code_hash).first()
    if link_code is None or not link_code.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link code.")

    other_player = (
        db.query(Player)
        .filter(Player.account_hash == payload.account_hash, Player.id != link_code.player_id)
        .first()
    )
    if other_player is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This game account is already linked to a different myscape account.",
        )

    link_code.used_at = datetime.now(timezone.utc)

    player = link_code.player
    player.account_hash = payload.account_hash
    if payload.runescape_name:
        player.runescape_name = payload.runescape_name

    raw_api_key = generate_token()
    api_key = PlayerApiKey(player_id=player.id, key_hash=hash_token(raw_api_key))
    db.add(api_key)
    db.commit()

    return LinkExchangeResponse(api_key=raw_api_key, player_id=player.id)
