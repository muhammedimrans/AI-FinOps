"""Shared HTTP transport layer for provider integrations — F-033."""

from __future__ import annotations

from app.http.auth import ApiKeyHeaderAuth, BearerTokenAuth, CompositeAuth, HttpAuth
from app.http.client import ProviderHttpClient, map_http_error
from app.http.retry import ExponentialRetryPolicy
from app.http.transport import HttpTransport, HttpxTransport

__all__ = [
    "ApiKeyHeaderAuth",
    "BearerTokenAuth",
    "CompositeAuth",
    "ExponentialRetryPolicy",
    "HttpAuth",
    "HttpTransport",
    "HttpxTransport",
    "ProviderHttpClient",
    "map_http_error",
]
