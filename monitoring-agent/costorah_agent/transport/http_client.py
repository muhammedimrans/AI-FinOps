"""
HttpClient — POSTs normalized usage events to COSTORAH's Usage Ingestion
API (EP-16), authenticated via an Organization API Key (EP-15).

TLS certificate validation is on by default (`verify_tls=True`) and should
only ever be disabled for local development against a self-signed backend
— never in production. The API key is sent exactly once per request, as
an Authorization header, and is never logged (see logging_setup.py's
redaction filter for the belt-and-suspenders guarantee).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


class IngestionOutcome(enum.Enum):
    """What happened to one event after a delivery attempt."""

    SUCCESS = "success"
    DUPLICATE = "duplicate"  # already ingested — treat identically to success
    AUTH_FAILED = "auth_failed"  # 401/403 — retrying won't help without config changes
    VALIDATION_FAILED = "validation_failed"  # 400/404/422 — payload itself is bad
    RETRYABLE_ERROR = "retryable_error"  # network error, timeout, 5xx


@dataclass(slots=True)
class IngestionResult:
    outcome: IngestionOutcome
    status_code: int | None
    detail: str
    usage_id: str | None = None

    @property
    def is_retryable(self) -> bool:
        return self.outcome == IngestionOutcome.RETRYABLE_ERROR


class HttpClient:
    """Thin async wrapper around the EP-16 ingestion endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        verify_tls: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            verify=verify_tls,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": _user_agent(),
            },
        )

    async def send_usage_event(self, payload: dict[str, Any]) -> IngestionResult:
        url = f"{self._endpoint}/v1/ingest/usage"
        try:
            resp = await self._client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            return IngestionResult(IngestionOutcome.RETRYABLE_ERROR, None, f"timeout: {exc}")
        except httpx.TransportError as exc:
            return IngestionResult(
                IngestionOutcome.RETRYABLE_ERROR, None, f"connection error: {exc}"
            )

        return self._interpret_response(resp)

    def _interpret_response(self, resp: httpx.Response) -> IngestionResult:
        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            duplicate = bool(body.get("duplicate", False))
            return IngestionResult(
                IngestionOutcome.DUPLICATE if duplicate else IngestionOutcome.SUCCESS,
                200,
                "duplicate" if duplicate else "ingested",
                usage_id=body.get("usage_id"),
            )
        if resp.status_code in (401, 403):
            return IngestionResult(
                IngestionOutcome.AUTH_FAILED, resp.status_code, _safe_detail(resp)
            )
        if resp.status_code in (400, 404, 422):
            return IngestionResult(
                IngestionOutcome.VALIDATION_FAILED, resp.status_code, _safe_detail(resp)
            )
        # 5xx and anything unexpected: assume transient, worth retrying.
        return IngestionResult(
            IngestionOutcome.RETRYABLE_ERROR, resp.status_code, _safe_detail(resp)
        )

    async def close(self) -> None:
        await self._client.aclose()


def _safe_detail(resp: httpx.Response) -> str:
    """Extract a short error detail without ever including the request body
    (which could contain the caller's own metadata) in a log-friendly form."""
    try:
        body = resp.json()
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail[:500]
    except ValueError:
        pass
    return f"HTTP {resp.status_code}"


def _user_agent() -> str:
    from costorah_agent.version import __version__

    return f"costorah-agent/{__version__}"
