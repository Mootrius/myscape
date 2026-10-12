"""Website signup/login/logout, forgot/reset password and signup email
verification (see PasswordResetToken and EmailVerificationToken in
app/models.py).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import site_flags
from app.auth import (
    get_current_account_from_session,
    get_optional_current_game_account_from_session,
    log_in_account,
    log_out_account,
)
from app.database import get_db
from app.email_client import send_email
from app.limiter import limiter
from app.models import (
    EMAIL_VERIFICATION_TOKEN_LIFETIME,
    PASSWORD_RESET_TOKEN_LIFETIME,
    Account,
    EmailVerificationToken,
    GameAccount,
    PasswordResetToken,
)
from app.schemas import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PlayerOut,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from app.security import generate_token, hash_password, hash_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["website-auth"])

# Vague and identical whether or not the email is registered (see
# forgot_password).
_FORGOT_PASSWORD_RESPONSE = {"detail": "If that email has an account, we've sent a password reset link."}


def _player_out_for(request: Request, db: Session, account: Account) -> PlayerOut:
    """PlayerOut mixes identity (id, email) and character (runescape_name,
    account_hash) fields. These endpoints deal with the website login (an
    Account), so the character fields come from the session's active
    GameAccount (get_optional_current_game_account_from_session in
    app/auth.py), not account.game_accounts[0]. Tolerates a None game_account
    (zero linked characters).
    """
    game_account = get_optional_current_game_account_from_session(request, db, account)
    return PlayerOut(
        id=account.id,
        email=account.email,
        runescape_name=game_account.runescape_name if game_account else None,
        account_hash=game_account.account_hash if game_account else None,
    )


def _issue_verification_token(db: Session, account: Account) -> str:
    """Token bookkeeping shared by signup, resend and change-email: deletes the
    account's previous outstanding verification tokens so only the latest link
    is valid. Returns the raw token for the verify_url; only its hash is
    stored (see hash_token in app/security.py).
    """
    db.query(EmailVerificationToken).filter(EmailVerificationToken.account_id == account.id).delete()
    raw_token = generate_token()
    expires_at = datetime.now(timezone.utc) + EMAIL_VERIFICATION_TOKEN_LIFETIME
    db.add(EmailVerificationToken(account_id=account.id, token_hash=hash_token(raw_token), expires_at=expires_at))
    db.commit()
    return raw_token


def _send_verification_email(request: Request, db: Session, account: Account) -> None:
    """Welcome email for signup and resend_verification_email (first-time
    verification). change_email uses _send_email_change_verification, with
    copy for an existing account.
    """
    raw_token = _issue_verification_token(db, account)
    verify_url = f"{str(request.base_url).rstrip('/')}/verify-email?token={raw_token}"
    send_email(
        to=account.email,
        subject="Confirm your myscape email address",
        html=(
            "<p>Welcome to myscape! Click the link below to confirm your email address "
            "and finish setting up your account.</p>"
            f'<p><a href="{verify_url}">Confirm my email address</a>. This link expires in 24 hours.</p>'
        ),
        text=(
            "Welcome to myscape! Click the link below to confirm your email address and "
            "finish setting up your account.\n\n"
            f"Confirm here: {verify_url}\n\n"
            "This link expires in 24 hours."
        ),
    )


def _send_email_change_verification(request: Request, db: Session, account: Account) -> None:
    """change_email's variant of _send_verification_email: same token issuing,
    copy for an account that already has a working login.
    """
    raw_token = _issue_verification_token(db, account)
    verify_url = f"{str(request.base_url).rstrip('/')}/verify-email?token={raw_token}"
    send_email(
        to=account.email,
        subject="Confirm your new myscape email address",
        html=(
            "<p>Your myscape account's email address was just changed to this one. "
            "Click the link below to confirm it and finish the change.</p>"
            f'<p><a href="{verify_url}">Confirm my new email address</a>. This link expires in 24 hours.</p>'
            "<p>Until you confirm, you'll need to verify before using most of the site.</p>"
        ),
        text=(
            "Your myscape account's email address was just changed to this one. Click the "
            "link below to confirm it and finish the change.\n\n"
            f"Confirm here: {verify_url}\n\n"
            "This link expires in 24 hours. Until you confirm, you'll need to verify before "
            "using most of the site."
        ),
    )


def _send_email_change_notice(old_email: str, new_email: str) -> None:
    """Heads-up sent to the OLD address when change_email succeeds. change_email
    does not bump token_version (an email change is not treated like a
    password change), so other sessions stay valid; this notice is how the
    previous owner learns of an unauthorized change and recovers.
    """
    send_email(
        to=old_email,
        subject="Your myscape email address was changed",
        html=(
            f"<p>The email on your myscape account was just changed from this address to <strong>{new_email}</strong>.</p>"
            "<p>If you made this change, there's nothing else to do.</p>"
            "<p>If you didn't, someone with your password may have access to your account. If you're still "
            "signed in anywhere else (another browser or device), go to Account and change your password "
            "right away -- that logs out every other session. This address has been removed from the "
            "account, so it can no longer be used to reset the password.</p>"
        ),
        text=(
            f"The email on your myscape account was just changed from this address to {new_email}.\n\n"
            "If you made this change, there's nothing else to do.\n\n"
            "If you didn't, someone with your password may have access to your account. If you're still "
            "signed in anywhere else (another browser or device), go to Account and change your password "
            "right away -- that logs out every other session. This address has been removed from the "
            "account, so it can no longer be used to reset the password."
        ),
    )


@router.post("/signup", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    # Sign-ups are switched off (see app/site_flags.py). Checked here as well as
    # on /signup, since anyone can POST directly.
    if not site_flags.SIGNUPS_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign ups are closed for now. myscape is coming soon.")
    existing = db.query(Account).filter(Account.email == payload.email).first()
    if existing is not None:
        # Deliberately vague: confirming an email is registered leaks
        # information.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create account.")

    account = Account(email=payload.email, password_hash=hash_password(payload.password))
    # Every Account gets one empty, unlinked GameAccount immediately
    # (account_hash/runescape_name NULL), so "signed up but not linked" is a
    # real row. The first link-code exchange fills it; only linking a second
    # character creates another (see docs/multi-account-scoping.md).
    account.game_accounts.append(GameAccount())
    db.add(account)
    db.commit()
    db.refresh(account)

    _send_verification_email(request, db, account)
    log_in_account(request, account)
    return _player_out_for(request, db, account)


@router.post("/login", response_model=PlayerOut)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.email == payload.email).first()

    # Run verify_password even for a missing account (against a fixed dummy
    # hash) so response time does not reveal which emails are registered.
    dummy_hash = "scrypt$16384$8$1$00$00"
    password_ok = verify_password(payload.password, account.password_hash if account else dummy_hash)

    if account is None or not account.password_hash or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    log_in_account(request, account)
    return _player_out_for(request, db, account)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request):
    log_out_account(request)


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Always returns the same generic message whether or not the email has an
    account (anti-enumeration, as in signup). Rate-limited tighter than
    login/signup (5/minute) because a hit sends a real email.
    
    Silently does nothing for an email with no account or an account with no
    password_hash (nullable for admin-created rows, see Account in
    app/models.py).
    
    Opportunistic cleanup: there is no scheduled job, so each call deletes all
    expired tokens and, before issuing a new one, this account's other
    outstanding tokens, so only the latest link is valid. reset_password
    deletes a token when it is consumed.
    """
    db.query(PasswordResetToken).filter(PasswordResetToken.expires_at < datetime.now(timezone.utc)).delete()
    # Committed on its own: the no-account branch below commits nothing, and the
    # cleanup would be rolled back.
    db.commit()

    account = db.query(Account).filter(Account.email == payload.email).first()
    if account is not None and account.password_hash:
        db.query(PasswordResetToken).filter(PasswordResetToken.account_id == account.id).delete()
        raw_token = generate_token()
        expires_at = datetime.now(timezone.utc) + PASSWORD_RESET_TOKEN_LIFETIME
        db.add(PasswordResetToken(account_id=account.id, token_hash=hash_token(raw_token), expires_at=expires_at))
        db.commit()

        reset_url = f"{str(request.base_url).rstrip('/')}/reset-password?token={raw_token}"
        send_email(
            to=account.email,
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
    """Consumes a forgot_password token exactly once and logs the account in (the
    user just proved control of the email).
    
    Bumps token_version to invalidate every other session (see app/models.py),
    which is what logs out whoever had access before the reset. log_in_account
    runs after the bump so the new session carries the fresh version.
    """
    token_hash = hash_token(payload.token)
    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    if reset_token is None or not reset_token.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link.")

    account = reset_token.account
    account.password_hash = hash_password(payload.password)
    account.token_version += 1
    # Single-use: the token is deleted once consumed.
    db.delete(reset_token)
    db.commit()

    log_in_account(request, account)
    return _player_out_for(request, db, account)


@router.post("/verify-email", response_model=PlayerOut)
@limiter.limit("10/minute")
def verify_email(request: Request, payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Consumes a signup/resend-verification token exactly once and logs the
    account in. The link may be opened in a different browser than the signup
    (see render_verify_email in app/pages/), so proving the token grants the
    session.
    """
    token_hash = hash_token(payload.token)
    verification_token = (
        db.query(EmailVerificationToken).filter(EmailVerificationToken.token_hash == token_hash).first()
    )
    if verification_token is None or not verification_token.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link.")

    account = verification_token.account
    account.email_verified_at = datetime.now(timezone.utc)
    db.delete(verification_token)
    db.commit()

    log_in_account(request, account)
    return _player_out_for(request, db, account)


@router.post("/resend-verification-email", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def resend_verification_email(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """For a signed-in, unverified account that lost its confirmation email
    (RESEND EMAIL button in render_verify_email_required, app/pages/). Uses
    the unverified-allowed login dependency (app/auth.py) rather than an email
    address. Rate-limited like forgot_password (5/minute) since it sends real
    email.
    
    A silent 204 no-op if already verified (e.g. a stale tab).
    """
    if not account.email_verified_at:
        _send_verification_email(request, db, account)


@router.post("/change-password", response_model=PlayerOut)
@limiter.limit("10/minute")
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Uses the unverified-allowed dependency: unverified users may change their
    password.
    
    Bumps token_version like reset_password: proving the current password is
    as strong a signal as a reset token, so every other session is logged out.
    log_in_account re-runs after the bump so this session stays valid.
    """
    if not account.password_hash or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    account.password_hash = hash_password(payload.new_password)
    account.token_version += 1
    db.commit()

    log_in_account(request, account)
    return _player_out_for(request, db, account)


@router.post("/change-email", response_model=PlayerOut)
@limiter.limit("10/minute")
def change_email(
    request: Request,
    payload: ChangeEmailRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Unverified-allowed on purpose: a mistyped signup email must be fixable
    without receiving a verification link.
    
    Requires the current password, since this change can hand the account to
    someone else if a session is hijacked. Resets email_verified_at to NULL
    and emails a new verification link, so the session goes back behind
    /verify-email-required (see get_current_verified_account_from_session in
    app/auth.py).
    """
    if not account.password_hash or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    existing = db.query(Account).filter(Account.email == payload.new_email, Account.id != account.id).first()
    if existing is not None:
        # Unlike signup, this caller is already a logged-in owner, so a specific
        # error leaks nothing.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already in use.")

    old_email = account.email
    account.email = payload.new_email
    account.email_verified_at = None
    db.commit()

    _send_email_change_verification(request, db, account)
    # Best-effort notice to the previous address, only if there was one
    # (admin-created rows may have no email, see Account in app/models.py) and
    # it differs from the new one.
    if old_email and old_email != account.email:
        _send_email_change_notice(old_email, account.email)
    return _player_out_for(request, db, account)


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Unverified-allowed, so a signup can be abandoned. Requires the current
    password, as in change_email. Everything the Account and its GameAccounts
    own (gear setups, mindmaps, loot events, storage snapshots, the RuneLite
    link) cascades on this delete (cascade="all, delete-orphan" in
    app/models.py), so one db.delete removes it all.
    """
    if not account.password_hash or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    log_out_account(request)
    db.delete(account)
    db.commit()


@router.get("/me", response_model=PlayerOut)
def read_logged_in_account(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    return _player_out_for(request, db, account)
