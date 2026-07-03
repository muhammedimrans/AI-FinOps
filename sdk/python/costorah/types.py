"""
Shared type/catalog definitions — kept separate from client.py so they can
be imported without pulling in the HTTP stack (e.g. by a future
instrumentation module that only needs to validate a provider name).

The provider catalog and UsageStatus values mirror
`backend/app/models/provider_connection.py::ProviderType` and
`backend/app/schemas/usage_ingestion.py::UsageStatus` (EP-16) exactly —
see `sdk/shared/API_CONTRACT.md`. This is a parallel, intentionally
matching definition, not a shared import: the SDK is an independently
distributable package and does not depend on the backend.
"""

from __future__ import annotations

from typing import Literal

SUPPORTED_PROVIDERS: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "grok",
        "google",
        "azure_openai",
        "openrouter",
        "ollama",
        "cohere",
        "bedrock",
        "mistral",
    }
)

UsageStatus = Literal["success", "error", "timeout", "cancelled"]
