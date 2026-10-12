"""Token/password hashing for account linking and website auth.

Link codes and plugin API keys are high-entropy random strings, so a fast
SHA-256 digest is right: bcrypt/scrypt only slow brute-forcing of low-entropy
human passwords, and their salted output cannot be looked up by equality,
which is needed here (the plugin sends the raw code/key and the matching row
is found by hash).
"""
import hashlib
import hmac
import secrets


def generate_token(nbytes: int = 24) -> str:
    """A URL-safe random token, 24 bytes (192 bits) by default for both link
    codes and API keys; they differ in lifetime and single-use, not length.
    """
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Password hashing
#
# A human-chosen password is low-entropy and must be assumed guessable offline
# if the database leaks, so it needs a slow, memory-hard hash. scrypt is in the
# stdlib (`hashlib`): no extra dependency or C-extension wheel to break on a
# Python bump. Cost parameters are stored with the hash so they can be raised
# without invalidating existing passwords.

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
