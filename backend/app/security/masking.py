"""Secret masking for API responses and logs (EP-22, Part 7).

Never used to protect data at rest (that's EncryptionService) — this is the
display-only transform applied when a masked representation of a credential
needs to leave the process (API response body) or enter a log line.
"""

from __future__ import annotations

_VISIBLE_PREFIX = 3
_VISIBLE_SUFFIX = 4
_MIN_LENGTH_FOR_PARTIAL_REVEAL = _VISIBLE_PREFIX + _VISIBLE_SUFFIX + 1


def mask_secret(value: str) -> str:
    """Return a masked representation of *value*, e.g. ``sk-********************************AbC``.

    Short values (too short to safely reveal a prefix and suffix without
    revealing the whole thing) are fully masked. This function only ever
    accepts an already-decrypted plaintext value transiently, in memory, for
    the immediate purpose of building the mask — the plaintext itself is
    never returned or logged.
    """
    if not value:
        return ""
    if len(value) < _MIN_LENGTH_FOR_PARTIAL_REVEAL:
        return "*" * len(value)
    prefix = value[:_VISIBLE_PREFIX]
    suffix = value[-_VISIBLE_SUFFIX:]
    stars = "*" * max(len(value) - _VISIBLE_PREFIX - _VISIBLE_SUFFIX, 8)
    return f"{prefix}{stars}{suffix}"
