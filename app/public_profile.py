"""Code generation for the public Character Overview (myscape.io/c/<code>; see
GameAccount.is_public_profile/public_code in app/models.py and the
/api/players/me/public-profile* endpoints and /c/{code} route in app/main.py).

The alphabet excludes 0/O and 1/I/l so a code can be read aloud over voice
chat and typed back. Codes are lowercase only and lookups are case-insensitive
(normalize_public_code).

31 characters ^ 5 is ~28.6 million codes, more than enough even after the
blocklist.
"""
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Friendship, GameAccount, _as_aware_utc, _utcnow

CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
CODE_LENGTH = 5

# Minimum time between POST .../regenerate-code calls, so a compromised session
# cannot rapid-fire invalidate a shared link. Checked against
# public_code_regenerated_at (app/models.py), never is_public_profile; toggling
# public/private is unthrottled.
PUBLIC_CODE_REGENERATE_COOLDOWN = timedelta(hours=24)

# Fresh candidates to try before giving up. Failing 500 independent draws means
# something is wrong (shrunken alphabet/length or an over-aggressive blocklist),
# so fail loudly.
_MAX_ATTEMPTS = 500

# Not exhaustive: enough that a generated code cannot be a real word or common
# slur. Matched as a substring (_contains_blocked_word), so "fuck" also blocks
# "fucky". Lowercase, like all comparisons here.
_BLOCKED_SUBSTRINGS = frozenset({
    # Profanity/slurs reachable with this alphabet (which already excludes
    # 0/1/i/l/o).
    "fuck", "shit", "cunt", "bitch", "cock", "dick", "pussy", "whore",
    "slut", "rape", "nazi", "fag", "dyke", "spic", "chink", "gook",
    "kike", "wank", "twat", "nigg", "retard",
    # Ordinary words that would read as unintentional ("tacos", "candy", ...)
    # rather than as a code.
    "taco", "candy", "sexy", "porn", "anal", "boob", "butt", "poop",
})


def normalize_public_code(raw: str) -> str:
    """Canonical form for a code from a URL or form field: lowercased and
    stripped. Every lookup against GameAccount.public_code goes through this,
    and generate_public_code emits only this form, so the column needs no
    case-insensitive index.
    """
    return raw.strip().lower()


def _contains_blocked_word(code: str) -> bool:
    return any(bad in code for bad in _BLOCKED_SUBSTRINGS)


def generate_public_code(db: Session) -> str:
    """Picks a fresh, unused, clean 5-character code. Checks the blocklist first
    (free) and the database second. Raises RuntimeError if all _MAX_ATTEMPTS
    candidates fail.
    """
    for _ in range(_MAX_ATTEMPTS):
        candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if _contains_blocked_word(candidate):
            continue
        exists = (
            db.query(GameAccount.id)
            .filter(GameAccount.public_code == candidate)
            .first()
            is not None
        )
        if not exists:
            return candidate
    raise RuntimeError("Could not generate a unique public profile code.")


def regenerate_cooldown_remaining(game_account: GameAccount) -> Optional[timedelta]:
    """None if a regenerate is allowed now; otherwise the remaining wait.
    public_code_regenerated_at is stamped on first assignment and on each
    regenerate, so this measures from the most recent. A null column is never
    throttled.
    """
    last = game_account.public_code_regenerated_at
    if last is None:
        return None
    elapsed = _utcnow() - _as_aware_utc(last)
    remaining = PUBLIC_CODE_REGENERATE_COOLDOWN - elapsed
    return remaining if remaining > timedelta(0) else None


def format_cooldown_remaining(remaining: timedelta) -> str:
    """Human-readable remaining time for the 429 detail message, rounded UP to
    whole hours so it never reads "0 hours".
    """
    hours = int(remaining.total_seconds() // 3600)
    if remaining.total_seconds() % 3600:
        hours += 1
    hours = max(hours, 1)
    return f"{hours} hour{'s' if hours != 1 else ''}"


def find_game_account_by_code(db: Session, raw_code: str) -> Optional[GameAccount]:
    """Resolves a code (any case) to its GameAccount whether or not the profile
    is public. For the friends feature, where the code doubles as the friend
    code. NEVER use this to decide who can see a Character Overview; use
    find_viewable_game_account.
    """
    normalized = normalize_public_code(raw_code)
    if not normalized:
        return None
    return db.query(GameAccount).filter(GameAccount.public_code == normalized).first()


def are_friends(db: Session, a_id, b_id) -> bool:
    """True if an *accepted* friendship exists between these characters, in
    either direction.
    """
    return (
        db.query(Friendship.id)
        .filter(
            Friendship.status == "accepted",
            (
                ((Friendship.requester_id == a_id) & (Friendship.addressee_id == b_id))
                | ((Friendship.requester_id == b_id) & (Friendship.addressee_id == a_id))
            ),
        )
        .first()
        is not None
    )


def find_viewable_game_account(db: Session, raw_code: str, viewer: Optional[GameAccount]) -> Optional[GameAccount]:
    """Resolves a code to a profile the viewer may see: a public profile, or a
    private one when the session's active character (`viewer`) is its owner or
    an accepted friend. None otherwise, the same result as "no such code", so
    the 404 leaks nothing.
    """
    game_account = find_game_account_by_code(db, raw_code)
    if game_account is None:
        return None
    if game_account.is_public_profile:
        return game_account
    if viewer is not None and (viewer.id == game_account.id or are_friends(db, viewer.id, game_account.id)):
        return game_account
    return None
