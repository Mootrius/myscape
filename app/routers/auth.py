"""Website signup/login/logout -- the real thing, replacing the old
developer-only "create a player by email" placeholder.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_player_from_session, log_in_player, log_out_player
from app.database import get_db
from app.limiter import limiter
from app.models import Player
from app.schemas import LoginRequest, PlayerOut, SignupRequest
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["website-auth"])


@router.post("/signup", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(Player).filter(Player.email == payload.email).first()
    if existing is not None:
        # Deliberately vague -- confirming an email is already registered
        # is itself information a website shouldn't hand out for free.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create account.")

    player = Player(email=payload.email, password_hash=hash_password(payload.password))
    db.add(player)
    db.commit()
    db.refresh(player)

    log_in_player(request, player)
    return player


@router.post("/login", response_model=PlayerOut)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.email == payload.email).first()

    # Run verify_password even on a missing account (against a fixed dummy
    # hash) so a login attempt for a nonexistent email takes about the same
    # time as one for a real email with the wrong password -- otherwise the
    # timing difference itself leaks which emails are registered.
    dummy_hash = "scrypt$16384$8$1$00$00"
    password_ok = verify_password(payload.password, player.password_hash if player else dummy_hash)

    if player is None or not player.password_hash or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    log_in_player(request, player)
    return player


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request):
    log_out_player(request)


@router.get("/me", response_model=PlayerOut)
def read_logged_in_player(player: Player = Depends(get_current_player_from_session)):
    return player
