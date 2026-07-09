"""HTTP authentication strategies — F-033.

Each strategy builds the headers dict for a single provider request.
Credentials are held as plain strings at this layer (resolved from SecretReference
by SecretResolver before reaching here); they are never logged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class HttpAuth(ABC):
    """Abstract auth strategy: produces headers for a single HTTP request."""

    @abstractmethod
    def headers(self) -> dict[str, str]: ...


class NullAuth(HttpAuth):
    """No authentication headers.

    Used by self-hosted providers with no API key (Ollama) and by providers
    whose key travels as a query parameter rather than a header (Google
    Gemini's ``?key=``, applied by the caller directly at the call site, not
    via this strategy).
    """

    def headers(self) -> dict[str, str]:
        return {}


class BearerTokenAuth(HttpAuth):
    """``Authorization: Bearer <token>`` — used by OpenAI."""

    __slots__ = ("_token",)

    def __init__(self, token: str) -> None:
        self._token = token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}


class ApiKeyHeaderAuth(HttpAuth):
    """Custom header auth — used by Anthropic (``x-api-key: <key>``)."""

    __slots__ = ("_header_name", "_key")

    def __init__(self, header_name: str, key: str) -> None:
        self._header_name = header_name
        self._key = key

    def headers(self) -> dict[str, str]:
        return {self._header_name: self._key}


class CompositeAuth(HttpAuth):
    """Merge multiple auth strategies into one header dict (last-write wins)."""

    def __init__(self, *strategies: HttpAuth) -> None:
        self._strategies = strategies

    def headers(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for strategy in self._strategies:
            result.update(strategy.headers())
        return result
