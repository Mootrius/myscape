"""Code generation for the public Character Overview feature
(myscape.io/c/<code> -- see GameAccount.is_public_profile/public_code's
own comments in app/models.py, and app/main.py's /api/players/me/
public-profile* endpoints and /c/{code} route for where this gets
used).

The alphabet deliberately excludes every character that's easy to
misread or mistype out loud -- 0/O, 1/I/l -- since the whole point of
this short a code (vs. e.g. a UUID) is that someone can read it to a
friend over voice chat and have them type it back correctly. Lookups
are case-insensitive on top of that (normalize_public_code lowercases
before every comparison, and generate_public_code only ever emits
lowercase), so there's no "was that a capital or lowercase L" ambiguity
left at all -- not that an L ever appears, since it's one of the
excluded letters.

31 usable characters (8 digits + 23 letters) ^ 5 is ~28.6 million
possible codes -- comfortably more than this app will ever need, even
before accounting for the blocklist below trimming a tiny fraction of
them.
"""
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.models import GameAccount

CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
CODE_LENGTH = 5

# How many fresh random candidates to try before giving up -- at this
# code length/alphabet size, colliding with an existing code or the
# blocklist on every single one of 500 independent draws is astronomically
# unlikely unless something's actually wrong (the alphabet/length
# constants got shrunk, or the blocklist got too aggressive), in which
# case failing loudly here beats spinning forever.
_MAX_ATTEMPTS = 500

# Not exhaustive, and not trying to be -- just enough that a randomly
# generated code can't land on a real English word or common slur/
# profanity a player would be unhappy to see as their own share link.
# Checked as a substring match (see _contains_blocked_word below), so a
# short blocked word still catches a 5-character code that merely
# contains it (e.g. "fuck" blocks "fucky" too), not just an exact
# 5-character match. Lowercase, since every comparison here is already
# normalized to lowercase.
_BLOCKED_SUBSTRINGS = frozenset({
    # Profanity/slurs (common ones reachable with this alphabet -- it
    # already excludes 0/1/i/l/o, which rules out a few others on its
    # own).
    "fuck", "shit", "cunt", "bitch", "cock", "dick", "pussy", "whore",
    "slut", "rape", "nazi", "fag", "dyke", "spic", "chink", "gook",
    "kike", "wank", "twat", "nigg", "retard",
    # Real/common words worth avoiding simply because they'd read as
    # unintentional ("tacos", "candy", ...) rather than as a code --
    # the request that started this feature specifically called out
    # "tacos" as an example of what shouldn't slip through.
    "taco", "candy", "sexy", "porn", "anal", "boob", "butt", "poop",
})


def normalize_public_code(raw: str) -> str:
    """Canonical form for any code coming in from a URL path or a form
    field -- lowercased and stripped, nothing else (the alphabet above
    has no case-ambiguous characters to begin with). Every lookup
    against GameAccount.public_code goes through this first, and
    generate_public_code below only ever emits strings already in this
    form, so the column itself never needs a separate case-insensitive
    index or collation to match it correctly."""
    return raw.strip().lower()


def _contains_blocked_word(code: str) -> bool:
    return any(bad in code for bad in _BLOCKED_SUBSTRINGS)


def generate_public_code(db: Session) -> str:
    """Picks a fresh, unused, clean 5-character code. Checked against
    the blocklist first (cheap, no DB round trip) and the database
    second (an actual collision is far rarer than a blocklist hit, so
    there's no point querying before the free check can reject a
    candidate outright). Raises RuntimeError on the vanishingly
    unlikely chance _MAX_ATTEMPTS candidates all fail -- see that
    constant's own comment."""
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


def find_public_game_account(db: Session, raw_code: str) -> Optional[GameAccount]:
    """Resolves a code from a URL (any case) to its GameAccount, or
    None if the code doesn't exist OR the profile isn't public right
    now -- deliberately the same result either way (see the 404s in
    app/main.py that use this), so a visitor poking at codes can't use
    the response to tell "wrong code" apart from "right code, private
    profile"."""
    normalized = normalize_public_code(raw_code)
    return (
        db.query(GameAccount)
        .filter(GameAccount.public_code == normalized, GameAccount.is_public_profile.is_(True))
        .first()
    )
