"""Website signup/login/logout -- the real thing, replacing the old
developer-only "create a player by email" placeholder. Also forgot-
password/reset-password and signup email verification (see
PasswordResetToken's and EmailVerificationToken's own docstrings in
app/models.py for why both are the same shape as account-linking's
LinkCode).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import (
    get_current_account_from_session,
    get_optional_current_game_account_from_session,
    log_in_account,
    log_out_account,
)
from app.database import get_db
from app.email_client import send_email
from app.limiter import limiter
from app import site_flags
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

# Deliberately vague and identical whether or not the email is actually
# registered -- see forgot_password's own docstring below for why.
_FORGOT_PASSWORD_RESPONSE = {"detail": "If that email has an account, we've sent a password reset link."}


def _player_out_for(request: Request, db: Session, account: Account) -> PlayerOut:
    """PlayerOut mixes identity (id, email) and character
    (runescape_name, account_hash) fields -- the shape the frontend
    already expected before the multi-account split (see
    docs/multi-account-scoping.md). These endpoints only ever deal
    with the website login (an Account), so this fills in
    runescape_name/account_hash from whichever GameAccount this
    session's own active one is (see
    get_optional_current_game_account_from_session in app/auth.py) --
    NOT just account.game_accounts[0], which would silently ignore a
    switch made via the account page's own Linked Accounts list (step
    7 of docs/multi-account-scoping.md) and always show the first-ever
    linked character instead of whichever one is actually active.
    Tolerates a None game_account (zero linked characters, now a real
    reachable state since that page's own Remove button can delete
    down to it) the same way every other caller of that dependency
    does."""
    game_account = get_optional_current_game_account_from_session(request, db, account)
    return PlayerOut(
        id=account.id,
        email=account.email,
        runescape_name=game_account.runescape_name if game_account else None,
        account_hash=game_account.account_hash if game_account else None,
    )


def _issue_verification_token(db: Session, account: Account) -> str:
    """The token bookkeeping shared by every case that needs a fresh
    verification link (signup, resend, and change-email below) --
    cleans up any of this account's previous outstanding verification
    tokens first, same reasoning as forgot_password's own cleanup, so
    only the most recently sent link is ever valid. Returns the raw
    (unhashed) token to build the actual verify_url with -- only its
    hash is ever stored (see hash_token's own docstring in
    app/security.py)."""
    db.query(EmailVerificationToken).filter(EmailVerificationToken.account_id == account.id).delete()
    raw_token = generate_token()
    expires_at = datetime.now(timezone.utc) + EMAIL_VERIFICATION_TOKEN_LIFETIME
    db.add(EmailVerificationToken(account_id=account.id, token_hash=hash_token(raw_token), expires_at=expires_at))
    db.commit()
    return raw_token


def _send_verification_email(request: Request, db: Session, account: Account) -> None:
    """Shared by signup (a brand new, unverified account) and
    resend_verification_email below (a signed-in account asking for a
    fresh link because the first one expired or never arrived) -- both
    genuinely first-time-verification cases, hence the "Welcome"
    copy. change_email has its own near-identical sibling below
    (_send_email_change_verification) with copy that fits an existing
    account moving to a new address instead."""
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
    """change_email's own version of _send_verification_email above --
    same token issuing, different copy: this account already has a
    working login, it's just moving to a new address, so this doesn't
    talk about "finishing setup" the way signup's welcome email
    does."""
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
    """The heads-up sent to the OLD address the moment change_email
    succeeds -- the new address already gets its own confirmation link
    (see _send_email_change_verification above), but nothing would
    otherwise ever tell whoever the *previous* address belonged to that
    it happened at all. change_email doesn't bump token_version (an
    email change alone isn't treated as the same kind of
    account-compromise signal a password change is -- see that
    endpoint's own docstring), so if this wasn't authorized, any other
    session the real owner is still signed in on stays valid -- which
    is exactly the recovery path this points them at, since this old
    address can no longer be used with forgot-password once it's off
    the account."""
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
    # Sign-ups are switched off for now (see app/site_flags.py for why
    # and how to turn them back on) -- checked here, not just by hiding
    # the form on /signup, since anyone can POST to this directly.
    if not site_flags.SIGNUPS_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign ups are closed for now. myscape is coming soon.")
    existing = db.query(Account).filter(Account.email == payload.email).first()
    if existing is not None:
        # Deliberately vague -- confirming an email is already registered
        # is itself information a website shouldn't hand out for free.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create account.")

    account = Account(email=payload.email, password_hash=hash_password(payload.password))
    # Every Account gets one empty, unlinked GameAccount immediately,
    # not created later by the link flow -- so "signed up but not yet
    # linked" is exactly what it's always been: a real row with
    # account_hash/runescape_name still NULL, never a missing one (see
    # docs/multi-account-scoping.md's "scope correction" section). The
    # first link-code exchange fills in this same row; only linking a
    # *second* character (the actual multi-account feature) ever
    # creates another one.
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

    # Run verify_password even on a missing account (against a fixed dummy
    # hash) so a login attempt for a nonexistent email takes about the same
    # time as one for a real email with the wrong password -- otherwise the
    # timing difference itself leaks which emails are registered.
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
    nullable for admin-created rows (see Account's own docstring), so
    this stays defensive rather than assuming that invariant forever.

    Also does a bit of opportunistic cleanup on its way through --
    there's no scheduled job runner in this app to sweep
    password_reset_tokens on a timer, so instead every call here
    deletes any tokens (for anyone) that have already expired, plus any
    other outstanding tokens for this specific account once one is
    about to be issued -- so only ever the most recently requested link
    is valid, and expired or superseded ones don't just pile up
    forever. A used token doesn't need this: reset_password deletes it
    directly the moment it's consumed."""
    db.query(PasswordResetToken).filter(PasswordResetToken.expires_at < datetime.now(timezone.utc)).delete()
    # Committed on its own since the branch below (no matching account,
    # or one with no password set) doesn't otherwise commit anything --
    # without this, that cleanup would just get silently rolled back
    # when this request's DB session closes.
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
    """Consumes a forgot_password token exactly once. Logs the account
    in immediately on success -- same reasoning as signup's own
    auto-login: someone who just proved they control the account's
    email and picked a new password came here to get back into their
    account, not to separately log in again right after.

    Also bumps the account's token_version, which invalidates every
    *other* session already logged in as this account (see that
    column's own docstring in app/models.py) -- if someone else had
    access to the account before this reset (the actual scenario a
    password reset exists to recover from), this is what actually logs
    them back out rather than leaving their existing session valid.
    log_in_account below runs after the bump, so it stamps *this*
    request's new session with the fresh version instead of the one
    that just got invalidated."""
    token_hash = hash_token(payload.token)
    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    if reset_token is None or not reset_token.is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link.")

    account = reset_token.account
    account.password_hash = hash_password(payload.password)
    account.token_version += 1
    # The token's only purpose was getting the account here once -- no
    # reason to keep a "used" row around forever (see forgot_password's
    # own cleanup of expired-but-unused ones above).
    db.delete(reset_token)
    db.commit()

    log_in_account(request, account)
    return _player_out_for(request, db, account)


@router.post("/verify-email", response_model=PlayerOut)
@limiter.limit("10/minute")
def verify_email(request: Request, payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Consumes a signup/resend-verification token exactly once. Logs
    the account in immediately on success -- same reasoning as
    reset_password's own auto-login just above: clicking a link from an
    email isn't necessarily happening in whatever browser/session
    originally signed up (see render_verify_email's own comment in
    app/pages.py), so proving control of the token is what grants a
    session here, not an existing one."""
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
    """For a signed-in but not-yet-verified account that didn't get (or
    lost) its original confirmation email -- the RESEND EMAIL button
    on render_verify_email_required in app/pages.py. Requires being
    logged in (the plain, unverified-allowed dependency -- see its own
    docstring in app/auth.py) rather than being keyed off an email
    address like forgot_password is, since the caller is necessarily
    already this exact account. Rate-limited the same as forgot_password
    (5/minute) for the same reason: a hit here costs a real outbound
    email.

    A silent no-op (but still a 204, not an error) if it's already
    verified, e.g. a stale tab -- there's nothing useful left for this
    button to do at that point."""
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
    """Base (unverified-allowed) dependency, not the verified-required
    one -- there's no reason someone who hasn't verified their email
    yet should be blocked from changing their password.

    Same token_version bump as reset_password's own (see that
    endpoint's docstring above) -- proving the *current* password is
    still exactly as trustworthy a "this is really the account owner"
    signal as a fresh reset-email token was, so this logs out every
    *other* session the same way. log_in_account re-runs after the bump
    so this request's own session picks up the fresh version instead
    of invalidating itself."""
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
    """Also base (unverified-allowed) -- deliberately reachable before
    verification, since mistyping your own email at signup is exactly
    the situation where you'd otherwise never be able to receive a
    verification link at all to unblock yourself any other way.

    Requires the current password (not just an active session) since
    this is the one change on this page that can hand the account to
    someone else entirely if a session were ever hijacked without it.
    Resets email_verified_at back to NULL and sends a fresh
    verification email to the new address -- same "prove you control
    it" bar a brand new signup has to clear, not a lesser one just
    because this account already existed. That does mean this
    session's own access to the verified-required parts of the site
    goes back behind /verify-email-required immediately after this
    succeeds, same as it would for a brand new signup -- see
    get_current_verified_account_from_session in app/auth.py."""
    if not account.password_hash or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    existing = db.query(Account).filter(Account.email == payload.new_email, Account.id != account.id).first()
    if existing is not None:
        # Same vagueness tradeoff as signup's own 409 doesn't apply here
        # -- signup can't say "that email is taken" without leaking
        # which emails are registered to *someone*, but this caller is
        # already a proven, logged-in account owner, so there's no new
        # information handed to a stranger by being specific.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already in use.")

    old_email = account.email
    account.email = payload.new_email
    account.email_verified_at = None
    db.commit()

    _send_email_change_verification(request, db, account)
    # Best-effort heads-up to whoever the address belonged to before --
    # only when there was one (an admin-created row can have no email
    # at all, see Account's own docstring in app/models.py) and it's
    # actually different from the new one (a same-email "change" is a
    # no-op this far down, but harmless to allow).
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
    """Base (unverified-allowed) dependency again -- an unverified
    account should still be able to walk away from a signup it decided
    not to finish. Requires the current password, same reasoning as
    change_email above. Every row this account (and each of its linked
    GameAccounts) owns -- gear setups, mindmaps, loot events, every
    storage snapshot, the RuneLite link itself, etc. -- cascades on
    this delete -- see each relationship's cascade="all, delete-orphan"
    on Account and GameAccount in app/models.py -- so this one
    db.delete is genuinely everything, not a partial wipe that leaves
    orphaned rows behind."""
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
