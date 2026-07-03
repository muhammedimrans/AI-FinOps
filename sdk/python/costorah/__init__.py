"""COSTORAH — official Python SDK for AI usage/cost telemetry.

    from costorah import Costorah

    client = Costorah(api_key="costorah_live_xxxxxxxxx")
    client.track(provider="openai", model="gpt-4.1", cost=0.041)

See https://github.com/muhammedimrans/ai-finops/tree/main/sdk/python for
the full quick start, configuration reference, and examples.
"""

from __future__ import annotations

from costorah.client import Costorah, TrackResult
from costorah.config import Config
from costorah.exceptions import (
    AuthenticationError,
    ConfigurationError,
    CostorahError,
    NetworkError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from costorah.version import __version__

__all__ = [
    "AuthenticationError",
    "Config",
    "ConfigurationError",
    "Costorah",
    "CostorahError",
    "NetworkError",
    "RateLimitError",
    "ServerError",
    "TrackResult",
    "ValidationError",
    "__version__",
]
