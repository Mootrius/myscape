"""Token generation/hashing for the account-linking system.

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
import secrets


def generate_token(nbytes: int = 24) -> str:
    """A URL-safe random token. 24 bytes (192 bits) by default -- plenty
    for both the short-lived link code and the long-lived API key; the
    difference between them is lifetime/single-use, not length."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
