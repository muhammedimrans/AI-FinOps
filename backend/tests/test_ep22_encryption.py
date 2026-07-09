"""Tests for EncryptionService, masking, and ProviderCredentialService (EP-22 Part 1/7).

All hermetic — no network, no database. Verifies:
  - encrypt()/decrypt() round-trip
  - tamper detection (InvalidToken -> EncryptionError, never a raw plaintext leak)
  - key rotation (APP_SECRET_KEY_PREVIOUS fallback)
  - masking never reveals the full secret
  - ProviderCredentialService never returns a plaintext key from masked()
"""

from __future__ import annotations

import pytest

from app.security.encryption import EncryptionError, EncryptionService
from app.security.masking import mask_secret
from app.services.provider_credential_service import ProviderCredentialService

_SECRET_A = "test-secret-key-for-testing-only-32ch"
_SECRET_B = "a-different-32-character-secret-key"


class TestEncryptionService:
    def test_round_trip(self) -> None:
        svc = EncryptionService(primary_secret=_SECRET_A)
        ciphertext = svc.encrypt("sk-abc123")
        assert svc.decrypt(ciphertext) == "sk-abc123"

    def test_ciphertext_does_not_contain_plaintext(self) -> None:
        svc = EncryptionService(primary_secret=_SECRET_A)
        ciphertext = svc.encrypt("sk-super-secret-value")
        assert "sk-super-secret-value" not in ciphertext

    def test_ciphertext_is_versioned(self) -> None:
        svc = EncryptionService(primary_secret=_SECRET_A)
        ciphertext = svc.encrypt("sk-abc123")
        assert ciphertext.startswith("v1:")

    def test_different_secrets_produce_undecryptable_ciphertext(self) -> None:
        svc_a = EncryptionService(primary_secret=_SECRET_A)
        svc_b = EncryptionService(primary_secret=_SECRET_B)
        ciphertext = svc_a.encrypt("sk-abc123")
        with pytest.raises(EncryptionError):
            svc_b.decrypt(ciphertext)

    def test_malformed_ciphertext_raises_encryption_error(self) -> None:
        svc = EncryptionService(primary_secret=_SECRET_A)
        with pytest.raises(EncryptionError):
            svc.decrypt("not-a-valid-ciphertext")

    def test_tampered_ciphertext_raises_encryption_error(self) -> None:
        svc = EncryptionService(primary_secret=_SECRET_A)
        ciphertext = svc.encrypt("sk-abc123")
        version, token = ciphertext.split(":", 1)
        tampered = f"{version}:{token[:-4]}AAAA"
        with pytest.raises(EncryptionError):
            svc.decrypt(tampered)

    def test_empty_plaintext_rejected(self) -> None:
        svc = EncryptionService(primary_secret=_SECRET_A)
        with pytest.raises(ValueError, match="empty"):
            svc.encrypt("")

    def test_rotation_previous_key_still_decrypts_old_ciphertext(self) -> None:
        """Simulates rotating APP_SECRET_KEY: old ciphertext, encrypted under
        the pre-rotation secret, must still decrypt once that secret is
        supplied as APP_SECRET_KEY_PREVIOUS on the new service instance."""
        old_svc = EncryptionService(primary_secret=_SECRET_A)
        old_ciphertext = old_svc.encrypt("sk-still-valid")

        rotated_svc = EncryptionService(primary_secret=_SECRET_B, previous_secret=_SECRET_A)
        assert rotated_svc.decrypt(old_ciphertext) == "sk-still-valid"

        # New encryptions use the new (current) key.
        new_ciphertext = rotated_svc.encrypt("sk-new-value")
        assert rotated_svc.decrypt(new_ciphertext) == "sk-new-value"

    def test_rotation_without_previous_key_cannot_decrypt_old_ciphertext(self) -> None:
        old_svc = EncryptionService(primary_secret=_SECRET_A)
        old_ciphertext = old_svc.encrypt("sk-orphaned")

        rotated_svc = EncryptionService(primary_secret=_SECRET_B)  # no previous_secret
        with pytest.raises(EncryptionError):
            rotated_svc.decrypt(old_ciphertext)


class TestMaskSecret:
    def test_masks_middle_of_long_key(self) -> None:
        masked = mask_secret("sk-" + "a" * 40 + "AbC")
        assert masked.startswith("sk-")
        assert masked.endswith("AbC")
        assert "*" in masked
        assert "a" * 10 not in masked

    def test_short_value_fully_masked(self) -> None:
        masked = mask_secret("short")
        assert masked == "*" * 5
        assert "s" not in masked

    def test_empty_value_returns_empty(self) -> None:
        assert mask_secret("") == ""

    def test_masked_value_never_equals_plaintext(self) -> None:
        plaintext = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
        assert mask_secret(plaintext) != plaintext


class TestProviderCredentialService:
    def test_encrypt_decrypt_round_trip(self) -> None:
        svc = ProviderCredentialService(EncryptionService(primary_secret=_SECRET_A))
        ciphertext = svc.encrypt("sk-abc123")
        assert svc.decrypt(ciphertext) == "sk-abc123"

    def test_masked_returns_none_for_no_credential(self) -> None:
        svc = ProviderCredentialService(EncryptionService(primary_secret=_SECRET_A))
        assert svc.masked(None) is None

    def test_masked_never_returns_plaintext(self) -> None:
        svc = ProviderCredentialService(EncryptionService(primary_secret=_SECRET_A))
        ciphertext = svc.encrypt("sk-proj-abcdefghijklmnopqrstuvwxyz")
        masked = svc.masked(ciphertext)
        assert masked is not None
        assert "abcdefghijklmnopqrstuvwxyz" not in masked
        assert masked.startswith("sk-")
