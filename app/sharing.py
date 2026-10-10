"""Code generation and lookup for myscape.io/s/<code> -- the generic,
many-per-account "share a frozen snapshot of some of my own data" link,
as distinct from GameAccount.public_code's own one-per-account,
always-live myscape.io/c/<code> link to Character Overview (see
app/public_profile.py). See SharedContent's own docstring in
app/models.py for the row this resolves.

10 characters (vs. public_code's 5) specifically because there will be
many more of these created over time than there will ever be public
Character Overview links -- per explicit instruction. Same alphabet
and blocklist as app/public_profile.py (imported from there rather
than duplicated, so updating one updates both), just a longer code:
31 usable characters ^ 10 is a little under 8 x 10^14 possible codes.
"""
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import SharedContent
from app.public_profile import CODE_ALPHABET, _contains_blocked_word

CODE_LENGTH = 10

# How long a share link stays resolvable after creation, for every
# content type -- not configurable per share (yet). A month felt like
# a reasonable starting point for "share this with a friend" without
# links piling up forever -- per explicit instruction to have some
# default expiration, revisit this constant if it turns out to be too
# short or too long in practice.
SHARE_DEFAULT_LIFETIME = timedelta(days=30)

# Same reasoning as public_profile.py's own _MAX_ATTEMPTS -- failing
# loudly here beats spinning forever if something's actually wrong.
_MAX_ATTEMPTS = 500

# Display label for the account page's Shared Links section's own
# TYPE column (see app/routers/account.py's list_shared_links) --
# every app that ever creates a SharedContent row needs an entry
# here, keyed by its own content_type string. Short, single-word
# labels per explicit instruction (not each app's own full feature
# name -- "Loot", not "Loot Tracker"; "Purchase", not "Purchase
# Goals") to keep this narrow column from forcing it wider than the
# Character/Code/Expiration columns around it. Not stored on the row
# itself since it's pure presentation, not data -- this is the one
# place that needs updating when a new app's share type is added,
# alongside that app's own POST .../share endpoint and its
# SharedContent.content_type value.
SHARE_CONTENT_TYPE_LABELS = {
    "loot_tracker": "Loot",
    "purchase_goal": "Purchase",
    "possessions": "Storages",
    "mindmap": "Mindmap",
    "goal_tracking": "Goals",
}


def generate_share_code(db: Session) -> str:
    """Picks a fresh, unused, clean 10-character code -- same
    blocklist-then-database check order as generate_public_code in
    app/public_profile.py (cheap in-memory check first, DB round trip
    only once that passes), see that function's own comment for why.
    Checked against SharedContent.code, never GameAccount.public_code
    -- the two code spaces are independent, so the same string could
    in principle exist in both at once with no conflict."""
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
    """Resolves a code from a URL (lowercased first, same normalize-
    before-lookup convention as normalize_public_code even though
    nothing in this alphabet is actually case-ambiguous) to its
    SharedContent row, or None if the code doesn't exist, has expired
    (see SharedContent.is_valid), or -- when the caller passes
    content_type, for a route that's specific to one app's own share
    kind -- doesn't match it. All three cases return the same None
    deliberately, so a visitor poking at codes (or an old link to
    something that's since expired) can't tell them apart."""
    normalized = raw_code.strip().lower()
    query = db.query(SharedContent).filter(SharedContent.code == normalized)
    if content_type is not None:
        query = query.filter(SharedContent.content_type == content_type)
    share = query.first()
    if share is None or not share.is_valid:
        # One of README's permanent example links? See
        # app/permanent_examples.py -- those keep resolving from a
        # frozen copy once the live row is gone or expired.
        from app.permanent_examples import find_permanent_share

        return find_permanent_share(db, normalized, content_type)
    return share
