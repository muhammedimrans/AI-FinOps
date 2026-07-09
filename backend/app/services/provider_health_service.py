"""ProviderHealthService — runs a validation probe and persists the result (EP-22, Part 4).

Bridges ``ProviderValidator`` (stateless — knows nothing about the database)
and ``ProviderConnectionRepository`` (knows nothing about provider APIs).
Used by both "save triggers immediate validation" (create/update) and the
explicit "Test Connection" / "Refresh Status" actions — the exact same
persistence logic backs all three, so the health fields can never drift
between them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.provider_connection import ProviderConnection
from app.providers.validation import ProviderValidator, ValidationResult
from app.repositories.provider_connection_repository import ProviderConnectionRepository


class ProviderHealthService:
    """Runs a live validation probe for a ProviderConnection and persists the outcome."""

    def __init__(self, validator: ProviderValidator | None = None) -> None:
        self._validator = validator or ProviderValidator()

    async def check_and_persist(
        self,
        repo: ProviderConnectionRepository,
        conn: ProviderConnection,
        *,
        api_key: str | None,
        base_url: str | None,
    ) -> ValidationResult:
        """Validate *conn*'s credential live, persist health fields, return the result."""
        result = await self._validator.validate(
            conn.provider_type, api_key=api_key, base_url=base_url
        )
        now = datetime.now(UTC)
        updates: dict[str, Any] = {
            "health_status": result.health_status,
            "last_validation_status": result.validation_status,
            "last_error": None if result.is_healthy else result.detail,
        }
        if result.is_healthy:
            updates["last_recovery_at"] = now
            updates["consecutive_failure_count"] = 0
        else:
            updates["last_failure_at"] = now
            updates["consecutive_failure_count"] = conn.consecutive_failure_count + 1
        await repo.update(conn, **updates)
        return result
