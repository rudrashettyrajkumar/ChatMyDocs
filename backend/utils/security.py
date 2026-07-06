"""Password hashing — PBKDF2-HMAC-SHA256 from the standard library.

Deliberately dependency-free: no bcrypt/argon2 C-extension to build, keeping the
container featherweight (CLAUDE.md) exactly like the "no local ML models" rule.
PBKDF2-HMAC-SHA256 at OWASP's recommended iteration count is a sound password KDF;
the cost is the iteration count, and verification is constant-time.

Stored format is a single self-describing string, so the iteration count can be
raised later without invalidating existing hashes:

    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000  # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
_SALT_BYTES = 16
_DKLEN = 32


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 hash for `password`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, _DKLEN)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of `password` against a stored hash.

    Returns False (never raises) on any malformed stored value — a corrupt hash
    is an auth failure, not a server error.
    """
    try:
        algo, iterations_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(dk, expected)
