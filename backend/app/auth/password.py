"""Argon2id password hashing — EP-05 / F-018."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Module-level singleton avoids re-instantiating the cost parameters on every call.
# Defaults: time_cost=3, memory_cost=65536 (64 MiB), parallelism=4, hash_len=32.
_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    """Return an Argon2id hash of the plain-text password."""
    return _ph.hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    """Return True when plain matches hashed; False on any mismatch or error."""
    try:
        _ph.verify(hashed, plain)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """Return True when the stored hash was produced with outdated parameters."""
    return _ph.check_needs_rehash(hashed)
