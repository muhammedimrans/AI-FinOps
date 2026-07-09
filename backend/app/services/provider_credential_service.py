"""ProviderCredentialService — encrypt/decrypt/mask boundary for provider API keys (EP-22).

The only place in the codebase permitted to call
``EncryptionService.decrypt()`` on a ``ProviderConnection.encrypted_api_key``
value. Every other layer (the API router, ``ProviderCredentialRepository``/
``ProviderConnectionRepository``, ``ProviderHealthService``) either passes an
already-encrypted string around or asks this service for a masked display
value — never a raw plaintext key outside the single in-memory scope of a
validation call (see ``ProviderValidator``, which receives the plaintext
directly from this service and never persists it).

Dependency inversion (EP-22 Part 1 requirement): this class depends on
``EncryptionService`` through its ``encrypt()``/``decrypt()`` interface only.
Swapping ``EncryptionService`` for a cloud-KMS-backed implementation later
requires no change here.
"""

from __future__ import annotations

from app.security.encryption import EncryptionService, get_encryption_service
from app.security.masking import mask_secret


class ProviderCredentialService:
    """Encrypt, decrypt, and mask provider API keys."""

    def __init__(self, encryption: EncryptionService | None = None) -> None:
        self._encryption = encryption or get_encryption_service()

    def encrypt(self, api_key: str) -> str:
        """Encrypt *api_key* for storage in ``ProviderConnection.encrypted_api_key``."""
        return self._encryption.encrypt(api_key)

    def decrypt(self, encrypted_api_key: str) -> str:
        """Decrypt a stored ciphertext. Callers must not log or return the result."""
        return self._encryption.decrypt(encrypted_api_key)

    def masked(self, encrypted_api_key: str | None) -> str | None:
        """Return a display-safe masked form (e.g. ``sk-***...***AbC``), or
        None if no credential is configured. Never returns the plaintext."""
        if not encrypted_api_key:
            return None
        plaintext = self._encryption.decrypt(encrypted_api_key)
        return mask_secret(plaintext)
