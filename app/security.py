"""Token/password hashing for the account-linking system and website auth.

Both the one-time link code and the long-lived plugin API key are
high-entropy random strings (not human-chosen passwords), so a plain,
fast SHA-256 digest is the right tool here -- not bcrypt/scrypt (those
exist to slow down brute-forcing a *low*-entropy human password, and as
a side effect their salted output can't be looked up by equality, which
we need: the plugin sends us the raw code/key and we have to find the
matching row by it). This is the same approach GitHub, Stripe, and
most API-key systems use for tokens, for exactly this reason.
"""
import hashlib
import hmac
import secrets


def generate_token(nbytes: int = 24) -> str:
    """A URL-safe random token. 24 bytes (192 bits) by default -- plenty
    for both the short-lived link code and the long-lived API key; the
    difference between them is lifetime/single-use, not length."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Password hashing -------------------------------------------------
#
# Passwords are the opposite case from the tokens above: a human picked
# it, so it's comparatively low-entropy and has to be assumed guessable
# offline if the database ever leaks. That calls for a *slow*,
# memory-hard hash, not a fast one -- scrypt (built into Python's
# stdlib `hashlib` since 3.6, no extra dependency, no C-extension wheel
# to break on a Render Python-version bump the way psycopg2 did) fits
# well here. The cost parameters are stored alongside the hash so they
# can be raised later without invalidating existing passwords.

_SCRYPT_N = 2**14  # CPU/memory cost factor (~16 MB, tens of ms per hash)
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(candidate, expected)
