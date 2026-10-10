"""The example links the README points at, kept alive permanently.

A shared snapshot (myscape.io/s/<code>) normally expires after
SHARE_DEFAULT_LIFETIME, vanishes when its owner deactivates it, and is
deleted with its character; a public profile (myscape.io/c/<code>) goes
dark when its owner makes it private or deletes the character. The codes
below are the exceptions: at startup, capture_permanent_examples copies
each one (if its source still exists and it hasn't been copied before)
into the PermanentExample table, which nothing else ever deletes, and the
lookups in app/sharing.py and app/main.py fall back to that copy
whenever the live row is gone.

To make another link permanent, add its code here and deploy -- while its
source still exists.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.models import GameAccount, PermanentExample, SharedContent

logger = logging.getLogger(__name__)

PERMANENT_SHARE_CODES = (
    "njnku7mnas",  # Loot Tracker
    "k3efa9ewsu",  # Purchase Goals
    "3fzrz7q5z2",  # Storages Viewer
    "5dc8c49ncb",  # Mindmaps
    "nysq229vq7",  # Goal Tracking
)
PERMANENT_PROFILE_CODES = ("mv7pu",)  # Character Overview

PROFILE_PARTS = ("summary", "progress", "skills", "collection-log")

# A permanent share's stand-in expires_at -- far enough out that
# SharedContent.is_valid is true for the foreseeable future.
_FAR_FUTURE = timedelta(days=365 * 100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def capture_permanent_examples(db: Session, profile_builders: Dict[str, Callable[[GameAccount], dict]]) -> None:
    """Copies every listed code that exists right now and isn't stored
    yet. Safe to run on every startup (already-stored codes are
    skipped); a code whose source is already gone is skipped with a
    warning. profile_builders maps each of PROFILE_PARTS to the same
    payload function the live public endpoints use, passed in from
    app/main.py so this module never imports it."""
    from fastapi.encoders import jsonable_encoder

    stored = {code for (code,) in db.query(PermanentExample.code).all()}

    for code in PERMANENT_SHARE_CODES:
        if code in stored:
            continue
        share = db.query(SharedContent).filter(SharedContent.code == code).first()
        if share is None:
            logger.warning("Permanent example share %s not found; nothing to copy.", code)
            continue
        owner = db.query(GameAccount).filter(GameAccount.id == share.game_account_id).first()
        db.add(
            PermanentExample(
                code=code,
                kind="share",
                content_type=share.content_type,
                owner_name=owner.runescape_name if owner else None,
                payload=share.payload,
            )
        )
        db.commit()
        logger.info("Captured permanent example share %s (%s).", code, share.content_type)

    for code in PERMANENT_PROFILE_CODES:
        if code in stored:
            continue
        game_account = db.query(GameAccount).filter(GameAccount.public_code == code).first()
        if game_account is None:
            logger.warning("Permanent example profile %s not found; nothing to copy.", code)
            continue
        payload = {part: jsonable_encoder(profile_builders[part](game_account)) for part in PROFILE_PARTS}
        db.add(
            PermanentExample(
                code=code,
                kind="profile",
                owner_name=game_account.runescape_name,
                payload=payload,
                model_glb=game_account.character_model_glb,
            )
        )
        db.commit()
        logger.info("Captured permanent example profile %s.", code)


def find_permanent_share(db: Session, raw_code: str, content_type: Optional[str] = None) -> Optional[SharedContent]:
    """The frozen copy of a permanent share as a transient (never
    added to the session) SharedContent, shaped like a live valid row
    -- or None if this isn't a permanent share code, or content_type
    is given and doesn't match. .frozen_owner_name carries the owner's
    display name for the page's "Shared by" line."""
    code = raw_code.strip().lower()
    row = db.query(PermanentExample).filter(PermanentExample.code == code, PermanentExample.kind == "share").first()
    if row is None or (content_type is not None and row.content_type != content_type):
        return None
    now = _utcnow()
    share = SharedContent(
        id=row.id,
        game_account_id=None,
        code=row.code,
        content_type=row.content_type,
        payload=row.payload,
        created_at=row.created_at or now,
        expires_at=now + _FAR_FUTURE,
    )
    share.frozen_owner_name = row.owner_name
    return share


def find_permanent_profile(db: Session, raw_code: str) -> Optional[PermanentExample]:
    code = raw_code.strip().lower()
    return db.query(PermanentExample).filter(PermanentExample.code == code, PermanentExample.kind == "profile").first()


def frozen_owner(owner_name: Optional[str], public_code: Optional[str] = None) -> GameAccount:
    """A transient GameAccount carrying just the fields the page
    renderers read (name, public code) -- never added to a session."""
    return GameAccount(runescape_name=owner_name, public_code=public_code)
