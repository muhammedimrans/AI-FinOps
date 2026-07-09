"""EncryptionService — symmetric encryption for provider credentials (EP-22).

Design
------
``EncryptionService`` is a small, dependency-inverted abstraction: callers
depend only on its ``encrypt()``/``decrypt()`` contract, never on the
underlying cryptographic primitive or key material. Today that primitive is
``cryptography.fernet.Fernet`` (AES-128-CBC + HMAC-SHA256, authenticated —
tampered or truncated ciphertext raises rather than silently returning
garbage), keyed by a value derived from ``APP_SECRET_KEY`` via PBKDF2-HMAC
(390k iterations, matching OWASP's current minimum for PBKDF2-SHA256) since
this codebase has no dedicated key-management system yet.

Swapping to a cloud KMS later (AWS KMS, Azure Key Vault, GCP KMS, HashiCorp
Vault) means writing a second class with the same ``encrypt()``/``decrypt()``
signatures and swapping the ``get_encryption_service()`` factory — no call
site (``ProviderCredentialService`` or any repository) changes, because none
of them import ``Fernet`` or know a key derivation happens at all.

Key rotation
------------
Every ciphertext is stored as ``"v<version>:<token>"``. ``decrypt()`` looks
up the Fernet keyed for that ciphertext's version; if unavailable it falls
back to an optional "previous" key built from ``APP_SECRET_KEY_PREVIOUS``.
This lets an operator rotate ``APP_SECRET_KEY`` (set the old value into
``APP_SECRET_KEY_PREVIOUS``, set a new ``APP_SECRET_KEY``) without a bulk
re-encryption migration — old rows keep decrypting via the previous key
until they are next re-saved (which re-encrypts under the current key, see
``ProviderCredentialService.rotate_key``).

Security invariants
--------------------
* The plaintext key is only ever held in memory for the duration of a single
  encrypt/decrypt call or a single outbound HTTP validation request — never
  written to logs, error messages, or persisted anywhere but the ciphertext
  column.
* ``decrypt()`` never appears in a log statement at any call site in this
  codebase (grep-verified — see CLAUDE.md §13's security section).
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings

_CURRENT_KEY_VERSION = 1
_PBKDF2_ITERATIONS = 390_000
_KDF_SALT = b"costorah-provider-credentials-v1"


class EncryptionError(Exception):
    """Raised when a ciphertext is malformed or cannot be decrypted with any known key."""


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte urlsafe-base64 Fernet key from an arbitrary-length secret."""
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        _KDF_SALT,
        _PBKDF2_ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(digest)


class EncryptionService:
    """encrypt()/decrypt() abstraction — see module docstring for design rationale."""

    def __init__(self, *, primary_secret: str, previous_secret: str | None = None) -> None:
        self._current_version = _CURRENT_KEY_VERSION
        self._fernets: dict[int, Fernet] = {
            self._current_version: Fernet(_derive_fernet_key(primary_secret)),
        }
        self._previous_fernet: Fernet | None = (
            Fernet(_derive_fernet_key(previous_secret)) if previous_secret else None
        )

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext*, returning an opaque versioned ciphertext string.

        Raises ValueError if *plaintext* is empty — callers must not encrypt
        an empty credential (that would silently mask a missing API key as
        "configured").
        """
        if not plaintext:
            raise ValueError("Cannot encrypt an empty value")
        token = self._fernets[self._current_version].encrypt(plaintext.encode("utf-8"))
        return f"v{self._current_version}:{token.decode('ascii')}"

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a value produced by ``encrypt()``.

        Tries the key matching the ciphertext's embedded version first, then
        falls back to the previous-generation key (rotation window). Raises
        ``EncryptionError`` — never a raw ``cryptography`` exception, and
        never includes the ciphertext or any derived key material in the
        exception message — if no known key can decrypt it.
        """
        try:
            version_str, token = ciphertext.split(":", 1)
            version = int(version_str.removeprefix("v"))
        except (ValueError, IndexError) as exc:
            raise EncryptionError("Malformed ciphertext") from exc

        candidates = [f for f in (self._fernets.get(version), self._previous_fernet) if f]
        if not candidates:
            raise EncryptionError(f"No decryption key available for ciphertext version {version}")

        for fernet in candidates:
            try:
                return fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except InvalidToken:
                continue
        raise EncryptionError("Unable to decrypt value with any known key")


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Return the process-wide EncryptionService singleton, built from Settings."""
    settings = get_settings()
    previous = getattr(settings, "app_secret_key_previous", None)
    return EncryptionService(
        primary_secret=settings.app_secret_key.get_secret_value(),
        previous_secret=previous.get_secret_value() if previous else None,
    )
