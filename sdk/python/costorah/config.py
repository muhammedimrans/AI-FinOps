"""
SDK configuration. A plain, validated dataclass rather than a full schema
library (unlike the backend/Monitoring Agent's pydantic-based config) —
the SDK's own dependency footprint is deliberately minimal (see
`README.md`'s Performance section), matching the "few lines of code,
first-party feel" goal of the ticket this ships under.
"""

from __future__ import annotations

from dataclasses import dataclass

from costorah.exceptions import ConfigurationError

_DEFAULT_ENDPOINT = "https://api.costorah.com"


@dataclass(frozen=True, slots=True)
class Config:
    """Validated SDK configuration. See `sdk/shared/API_CONTRACT.md` for
    the exact meaning of each field — every COSTORAH SDK exposes the same
    keys with the same defaults."""

    api_key: str
    endpoint: str = _DEFAULT_ENDPOINT
    timeout: float = 30.0
    batch_size: int = 25
    flush_interval: float = 5.0
    max_retries: int = 3
    verify_tls: bool = True

    # EP-18.3 reliability layer — see sdk/docs/RELIABILITY.md.
    queue_size: int = 10_000
    overflow_policy: str = "drop_oldest"
    persistent_queue: bool = False
    compression: bool = True
    retry: bool = True

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ConfigurationError("api_key is required")
        if not self.api_key.startswith("costorah_live_"):
            raise ConfigurationError("api_key must start with 'costorah_live_'")
        if not self.endpoint.startswith(("http://", "https://")):
            raise ConfigurationError("endpoint must start with http:// or https://")
        object.__setattr__(self, "endpoint", self.endpoint.rstrip("/"))
        if self.timeout <= 0:
            raise ConfigurationError("timeout must be positive")
        if self.batch_size <= 0:
            raise ConfigurationError("batch_size must be positive")
        if self.flush_interval <= 0:
            raise ConfigurationError("flush_interval must be positive")
        if self.max_retries < 0:
            raise ConfigurationError("max_retries must be >= 0")
        if self.queue_size <= 0:
            raise ConfigurationError("queue_size must be positive")
        if self.overflow_policy not in ("drop_newest", "drop_oldest", "block"):
            raise ConfigurationError(
                "overflow_policy must be one of: drop_newest, drop_oldest, block"
            )
