"""
Tests for app.core.validators — domain-level validation utilities.

Covers the provider configuration validator (H-002):
  - Exact prohibited key names are rejected
  - Case and separator normalisation works
  - Safe keys are accepted
  - Multiple violations are reported together
  - Empty and None-equivalent configs are accepted
"""
from __future__ import annotations

import pytest

from app.core.validators import validate_provider_configuration


class TestValidateProviderConfiguration:
    # ── Safe configurations ───────────────────────────────────────────────────

    def test_empty_dict_is_valid(self) -> None:
        validate_provider_configuration({})  # must not raise

    def test_safe_keys_are_accepted(self) -> None:
        validate_provider_configuration(
            {
                "base_url": "https://api.openai.com/v1",
                "timeout_seconds": 30,
                "max_retries": 3,
                "model_alias": "gpt-4o",
                "rate_limit_tier": "tier-1",
            }
        )

    def test_non_secret_metadata_is_accepted(self) -> None:
        validate_provider_configuration(
            {
                "region": "us-east-1",
                "deployment_id": "gpt-4-deploy",
                "api_version": "2024-02-01",
                "organization_id": "org-abc123",
            }
        )

    # ── Exact prohibited keys ─────────────────────────────────────────────────

    def test_api_key_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            validate_provider_configuration({"api_key": "sk-..."})

    def test_secret_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="secret"):
            validate_provider_configuration({"secret": "s3cr3t"})

    def test_password_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="password"):
            validate_provider_configuration({"password": "hunter2"})

    def test_access_token_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="access_token"):
            validate_provider_configuration({"access_token": "tok_..."})

    def test_refresh_token_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="refresh_token"):
            validate_provider_configuration({"refresh_token": "ref_..."})

    def test_bearer_token_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="bearer_token"):
            validate_provider_configuration({"bearer_token": "Bearer ..."})

    def test_client_secret_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="client_secret"):
            validate_provider_configuration({"client_secret": "cs_..."})

    def test_private_key_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="private_key"):
            validate_provider_configuration({"private_key": "-----BEGIN RSA..."})

    def test_token_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="token"):
            validate_provider_configuration({"token": "abc123"})

    def test_credentials_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="credential"):
            validate_provider_configuration({"credentials": {"key": "value"}})

    # ── Case and separator normalisation ──────────────────────────────────────

    def test_uppercase_key_is_normalised(self) -> None:
        with pytest.raises(ValueError):
            validate_provider_configuration({"API_KEY": "sk-..."})

    def test_mixed_case_is_normalised(self) -> None:
        with pytest.raises(ValueError):
            validate_provider_configuration({"ApiKey": "sk-..."})

    def test_hyphen_separator_is_normalised(self) -> None:
        with pytest.raises(ValueError):
            validate_provider_configuration({"api-key": "sk-..."})

    def test_space_separator_is_normalised(self) -> None:
        with pytest.raises(ValueError):
            validate_provider_configuration({"api key": "sk-..."})

    # ── Multiple violations ───────────────────────────────────────────────────

    def test_multiple_violations_reported_together(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            validate_provider_configuration(
                {
                    "api_key": "sk-...",
                    "secret": "s3cr3t",
                    "base_url": "https://api.openai.com/v1",  # safe
                }
            )
        message = str(exc_info.value)
        assert "api_key" in message
        assert "secret" in message
        # safe key must NOT appear in the error
        assert "base_url" not in message

    # ── Error message quality ─────────────────────────────────────────────────

    def test_error_message_mentions_secrets_store(self) -> None:
        with pytest.raises(ValueError, match="Secrets store"):
            validate_provider_configuration({"api_key": "sk-..."})

    def test_error_message_is_actionable(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)prohibited"):
            validate_provider_configuration({"password": "x"})
