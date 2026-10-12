"""Code generation and lookup for myscape.io/s/<code>: the generic,
many-per-account link to a frozen snapshot of some of a player's data, as
distinct from GameAccount.public_code's one-per-account live /c/<code> link
(app/public_profile.py). See SharedContent in app/models.py for the row this
resolves.

Codes are 10 characters (many more shares than public profiles will exist),
using the alphabet and blocklist imported from app/public_profile.py: 31^10 is
just under 8 x 10^14 codes.
"""
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import SharedContent
from app.public_profile import CODE_ALPHABET, _contains_blocked_word

CODE_LENGTH = 10

# How long a share link stays resolvable, for every content type (not
# configurable per share).
SHARE_DEFAULT_LIFETIME = timedelta(days=30)

# As in public_profile.py's _MAX_ATTEMPTS: fail loudly rather than spin.
_MAX_ATTEMPTS = 500

# Display label for the TYPE column of the account page's Shared Links section
# (list_shared_links in app/routers/account.py), keyed by content_type. Every
# app that creates a SharedContent row needs an entry, alongside its POST
# .../share endpoint. Labels are single words ("Loot", "Purchase") to keep the
# column narrow. Presentation only, so not stored on the row.
SHARE_CONTENT_TYPE_LABELS = {
    "loot_tracker": "Loot",
    "purchase_goal": "Purchase",
    "possessions": "Storages",
    "mindmap": "Mindmap",
    "goal_tracking": "Goals",
}


def generate_share_code(db: Session) -> str:
    """Picks a fresh, unused, clean 10-character code, checking the blocklist
    before the database, as generate_public_code does (app/public_profile.py).
    Checked against SharedContent.code only; the share and public_code spaces
    are independent.
    """
    for _ in range(_MAX_ATTEMPTS):
        candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if _contains_blocked_word(candidate):
            continue
        exists = (
            db.query(SharedContent.id)
            .filter(SharedContent.code == candidate)
            .first()
            is not None
        )
        if not exists:
            return candidate
    raise RuntimeError("Could not generate a unique share code.")


def find_valid_share(db: Session, raw_code: str, content_type: Optional[str] = None) -> Optional[SharedContent]:
    """Resolves a URL code (lowercased first, as normalize_public_code does) to
    its SharedContent row, or None if the code does not exist, has expired
    (SharedContent.is_valid), or does not match `content_type` (for routes
    specific to one share kind). All three return the same None so visitors
    cannot tell them apart.
    """
    normalized = raw_code.strip().lower()
    query = db.query(SharedContent).filter(SharedContent.code == normalized)
    if content_type is not None:
        query = query.filter(SharedContent.content_type == content_type)
    share = query.first()
    if share is None or not share.is_valid:
        # One of README's permanent example links (app/permanent_examples.py)?
        # Those keep resolving from a frozen copy once the live row is gone or
        # expired.
        from app.permanent_examples import find_permanent_share

        return find_permanent_share(db, normalized, content_type)
    return share
