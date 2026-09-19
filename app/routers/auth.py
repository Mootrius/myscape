"""Website signup/login/logout -- the real thing, replacing the old
developer-only "create a player by email" placeholder. Also forgot-
password/reset-password (see PasswordResetToken's own docstring in
app/models.py for why that's the same shape as account-linking's
LinkCode).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_player_from_session, log_in_player, log_out_player
from app.database import get_db
from app.email_client import send_email
from app.limiter import limiter
from app.models import PASSWORD_RESET_TOKEN_LIFETIME, PasswordResetToken, Player
from app.schemas import ForgotPasswordRequest, LoginRequest, PlayerOut, ResetPasswordRequest, SignupRequest
from app.security import generate_token, hash_password, hash_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["website-auth"])

# Deliberately vague and identical whether or not the email is actually
# registered -- see forgot_password's own docstring below for why.
_FORGOT_PASSWORD_RESPONSE = {"detail": "If that email has an account, we've sent a password reset link."}


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


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Always returns the same generic message regardless of whether
    payload.email actually has an account -- same anti-enumeration
    reasoning as signup's "Could not create account." above, just
    applied to a 200 instead of a 409 here since there's no failure
    state a legitimate caller needs to distinguish (unlike signup,
    where the caller genuinely needs to know their signup didn't go
    through). Rate-limited tighter than login/signup (5/minute vs
    10/minute) since a hit here costs a real outbound email rather
    than just a database lookup -- still plenty for a real player who
    mistypes their email and wants to retry.

    Silently does nothing (but still returns the same response) for an
    email with no account, or an account with no password_hash at all
    -- the latter shouldn't currently exist since linking a game
    account already requires being logged in first (see
    app/routers/linking.py's start_link), but password_hash is
    nullable for admin-created rows (see Player's own docstring), so
    this stays defensive rather than assuming that invariant forever."""
    # TEMPORARY: bypasses Python logging entirely (print, not log.*) to
    # rule out a Render log-viewer filter hiding our normal logging --
    # remove once the "email never arrives" issue is root-caused.
    player = db.query(Player).filter(Player.email == payload.email).first()
    print(f"[DEBUG forgot-password] email={payload.email!r} player_found={player is not None} "
          f"has_password_hash={bool(player and player.password_hash)}", flush=True)
    if player is not None and player.password_hash:
        raw_token = generate_token()
        expires_at = datetime.now(timezone.utc) + PASSWORD_RESET_TOKEN_LIFETIME
        db.add(PasswordResetToken(player_id=player.id, token_hash=hash_token(raw_token), expires_at=expires_at))
        db.commit()
        print("[DEBUG forgot-password] token stored, about to call send_email", flush=True)

        reset_url = f"{str(request.base_url).rstrip('/')}/reset-password?token={raw_token}"
        send_email(
            to=player.email,
            subject="Reset your myscape password",
            html=(
                f"<p>Someone (hopefully you) asked to reset the password on your myscape account.</p>"
                f'<p><a href="{reset_url}">Click here to choose a new password</a>. '
                f"This link expires in an hour and only works once.</p>"
                f"<p>If you didn't request this, you can safely ignore this email --"
                f" your password hasn't been changed.</p>"
            ),
            text=(
                "Someone (hopefully you) asked to reset the password on your myscape account.\n\n"
                f"Reset it here: {reset_url}\n\n"
                "This link expires in an hour and only works once.\n\n"
                "If you didn't request this, you can safely ignore this email -- your password "
                "hasn't been changed."
            ),
        )

    return _FORGOT_PASSWORD_RESPONSE


@router.post("/reset-password", response_model=PlayerOut)
@limiter.limit("10/minute")
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Consumes a forgot_password token exactly once. Logs the player
    in immediately on success -- same reasoning as signup's own
    auto-login: someone who just proved they control the account's
    email and picked a new password came here to get back into their
    account, not to separately log in again right after."""
    token_hash = hash_token(payload.token)
    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    if reset_token is None or not reset_token.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link.")

    reset_token.used_at = datetime.now(timezone.utc)
    player = reset_token.player
    player.password_hash = hash_password(payload.password)
    db.commit()

    log_in_player(request, player)
    return player


@router.get("/me", response_model=PlayerOut)
def read_logged_in_player(player: Player = Depends(get_current_player_from_session)):
    return player
