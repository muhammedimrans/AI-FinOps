"""OpenRouter provider adapter — EP-22 (validation), EP-06 (catalog/capabilities),
EP-26.0.1 (live model catalog + usage import).

Authentication
--------------
``Authorization: Bearer <api_key>``.

Live API calls
---------------
``GET /models`` — the models endpoint named in the EP-22 spec. Note this
endpoint is unauthenticated on OpenRouter's side (it returns the same public
catalog regardless of the key supplied), so a successful response confirms
reachability but not key validity; a genuinely invalid key is only caught
on a later completion call. This is disclosed rather than silently treated
as a stronger guarantee than it is — see CLAUDE.md §13's per-provider
validation-strength note. As of EP-26.0.1, this same endpoint also powers
``list_models()`` (live catalog, replacing the old static 4-model list).

``GET /api/v1/activity`` — usage import (EP-26.0.1). See ``get_usage()``'s
own docstring for the full, disclosed uncertainty around this endpoint's
exact response schema and required credential privilege — CLAUDE.md's
EP-26.0/EP-26.0.1 sections document the underlying research in full.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.http.auth import BearerTokenAuth
from app.http.client import ProviderHttpClient
from app.http.transport import HttpxTransport
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.credential import CredentialValidator, SecretResolver
from app.providers.errors import AuthenticationError
from app.providers.interface import AIProvider
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
    UsageData,
)

if TYPE_CHECKING:
    from app.providers.info import ProviderInfo
    from app.providers.models import UsagePage

log = structlog.get_logger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"

# EP-26.0's research (CLAUDE.md) found /api/v1/activity's own documentation
# states it returns "the last 30 (completed) UTC days" — this bounds how far
# back a single get_usage() call will actually iterate, regardless of the
# start_date requested, so a very old checkpoint can never trigger an
# unbounded request loop against an endpoint that would just 404/empty
# past this window anyway.
_ACTIVITY_RETENTION_DAYS = 30

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=False,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=False,
    supports_fine_tuning=False,
    supports_function_calling=True,
    max_context_window=200000,
    supported_model_ids=frozenset(
        {
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet",
            "google/gemini-pro-1.5",
            "meta-llama/llama-3.1-405b-instruct",
        }
    ),
)

# EP-26.0.1: this static list is now only a fallback, used by list_models()
# when the live GET /models call fails (network error, etc.) — the primary
# path calls the live catalog directly. Kept intentionally small and
# unmaintained beyond that fallback role, since OpenRouter's real catalog
# (dozens of models across a dozen-plus vendors, refreshed routinely) would
# make a hand-maintained list stale almost immediately — exactly the
# staleness risk CLAUDE.md's EP-26.0 research flagged for both this
# provider and Google's.
_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="openai/gpt-4o",
        display_name="GPT-4o (via OpenRouter)",
        provider_type="openrouter",
        context_window=128000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="anthropic/claude-3-5-sonnet",
        display_name="Claude 3.5 Sonnet (via OpenRouter)",
        provider_type="openrouter",
        context_window=200000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="google/gemini-pro-1.5",
        display_name="Gemini 1.5 Pro (via OpenRouter)",
        provider_type="openrouter",
        context_window=2000000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="meta-llama/llama-3.1-405b-instruct",
        display_name="Llama 3.1 405B (via OpenRouter)",
        provider_type="openrouter",
        context_window=131072,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


def _model_from_live_catalog(item: dict[str, Any]) -> ModelMetadata:
    """Map one item from OpenRouter's live ``GET /models`` response into
    ``ModelMetadata`` (EP-26.0.1). OpenRouter's model IDs are already the
    ``vendor/model`` slug (e.g. ``"anthropic/claude-sonnet-4"``) — the same
    convention this codebase's ``UsageCostRecord.model``/``ModelPricing.model``
    columns already store verbatim (CLAUDE.md's EP-26.0 Part 2 "Data
    Mapping" finding: no parsing or new column needed to store this
    correctly, only to *display* the vendor/model split, which is a
    frontend-layer concern — see ``parse_openrouter_model_id`` equivalent
    in ``apps/dashboard``).
    """
    model_id = str(item["id"])
    architecture = item.get("architecture") or {}
    modality = str(architecture.get("modality") or "")
    supported_params = {str(p).lower() for p in (item.get("supported_parameters") or [])}

    capabilities: set[ModelCapabilityFlag] = {ModelCapabilityFlag.STREAMING}
    if "tools" in supported_params or "tool_choice" in supported_params:
        capabilities.add(ModelCapabilityFlag.TOOL_CALLING)
        capabilities.add(ModelCapabilityFlag.FUNCTION_CALLING)
    if "image" in modality:
        capabilities.add(ModelCapabilityFlag.VISION)
    if "audio" in modality:
        capabilities.add(ModelCapabilityFlag.AUDIO)

    pricing = item.get("pricing") or {}
    prompt_price = pricing.get("prompt")
    completion_price = pricing.get("completion")

    def _per_1k(raw: str | float | int | None) -> float | None:
        # OpenRouter publishes pricing as a per-token dollar string (e.g.
        # "0.000003"); ModelMetadata's cost fields are per-1k-tokens.
        if raw is None:
            return None
        try:
            return float(raw) * 1000
        except (TypeError, ValueError):
            return None

    context_length = item.get("context_length")

    return ModelMetadata(
        id=model_id,
        display_name=str(item.get("name") or model_id),
        provider_type="openrouter",
        context_window=int(context_length) if context_length else None,
        max_output_tokens=None,
        capabilities=frozenset(capabilities),
        input_cost_per_1k=_per_1k(prompt_price),
        output_cost_per_1k=_per_1k(completion_price),
    )


class OpenRouterProvider(AIProvider):
    """OpenRouter provider adapter (EP-22, EP-26.0.1)."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._healthy: bool = False
        self._last_checked: datetime | None = None
        self._transport = HttpxTransport(
            base_url=config.base_url or _BASE_URL,
            verify=True,
            mock_transport=http_transport,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENROUTER

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _build_client(self, api_key: str) -> ProviderHttpClient:
        return ProviderHttpClient(
            base_url=self._config.base_url or _BASE_URL,
            auth=BearerTokenAuth(api_key),
            provider_type="openrouter",
            timeout=self._config.timeout_seconds,
            transport=self._transport,
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            raise AuthenticationError(
                "OpenRouter provider has no api_key_ref configured",
                provider_type="openrouter",
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="openrouter")

    async def verify_auth(self) -> bool:
        """Live GET /models — see module docstring for the validation-strength caveat."""
        key = self._resolve_key()
        CredentialValidator.validate_openrouter_key(key)
        async with self._build_client(key) as client:
            await client.get("/models")
        return True

    async def check_connection(self) -> ConnectionStatus:
        start = time.monotonic()
        try:
            await self.verify_auth()
            latency = round((time.monotonic() - start) * 1000, 2)
            self._healthy = True
            self._last_checked = datetime.now(UTC)
            return ConnectionStatus(
                is_connected=True,
                health_status=HealthStatus.HEALTHY,
                latency_ms=latency,
                checked_at=self._last_checked,
            )
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            self._healthy = False
            self._last_checked = datetime.now(UTC)
            return ConnectionStatus(
                is_connected=False,
                health_status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                error_message=str(exc),
                checked_at=self._last_checked,
            )

    async def check_capability(self, capability: str) -> bool:
        cap = capability.lower()
        return getattr(_CAPABILITIES, f"supports_{cap}", False) or getattr(
            _CAPABILITIES, cap, False
        )

    async def list_models(self) -> list[ModelMetadata]:
        """Live GET /models catalog (EP-26.0.1), falling back to the small
        static ``_MODELS`` list on any network/parse failure — matching the
        same "live call, static fallback only on error" shape
        ``OpenAIProvider.list_models()`` already established, rather than a
        second, differently-shaped pattern.

        OpenRouter's own ``/models`` response already carries per-model
        context length and per-token pricing (unlike most other providers'
        model-list endpoints) — both are mapped directly into
        ``ModelMetadata`` here rather than requiring a second, separately
        seeded enrichment table.

        Unlike OpenAI's ``list_models()``, a missing credential is not
        treated as fatal here — ``/models`` is documented as unauthenticated
        on OpenRouter's side (see the module docstring), so the catalog can
        still be fetched with no key at all; falling back to the static
        list on a missing/unresolvable key (rather than raising) also
        preserves this method's pre-EP-26.0.1 contract of never requiring a
        credential just to browse the model catalog.
        """
        try:
            key = self._resolve_key()
        except Exception as exc:
            log.warning("openrouter_no_credential_for_model_catalog", error_type=type(exc).__name__)
            key = ""

        try:
            async with self._build_client(key) as client:
                data = await client.get("/models")
        except Exception as exc:
            log.warning(
                "openrouter_live_model_catalog_unavailable",
                error_type=type(exc).__name__,
            )
            return list(_MODELS)

        raw_models: list[dict[str, Any]] = data.get("data", [])
        models: list[ModelMetadata] = []
        for item in raw_models:
            model_id = item.get("id")
            if not model_id:
                continue
            models.append(_model_from_live_catalog(item))
        return models or list(_MODELS)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> OpenRouterProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Submit a chat completion request — EP-25.4 (AI Playground).

        POST /chat/completions — OpenAI-compatible, since OpenRouter is a
        gateway in front of dozens of vendors using that one request shape.
        ``model_id`` is the ``vendor/model`` slug (e.g.
        ``anthropic/claude-sonnet-4``) OpenRouter's own catalog already uses.
        """
        key = self._resolve_key()
        payload: dict[str, Any] = {
            "model": request.model_id,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "stream": False,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        payload.update(request.extra)

        async with self._build_client(key) as client:
            data = await client.post("/chat/completions", json=payload)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return ProviderResponse(
            model_id=data.get("model", request.model_id),
            content=message.get("content") or "",
            usage=UsageData(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason"),
            raw_response=data,
        )

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """Real usage import via ``GET /api/v1/activity`` (EP-26.0.1),
        superseding EP-24.3's "always empty" no-op for this provider.

        Disclosed uncertainty — read before trusting this in production
        --------------------------------------------------------------
        EP-26.0's research (CLAUDE.md's EP-26.0/EP-26.0.1 sections)
        identified ``GET /api/v1/activity`` — beyond the ``/api/v1/credits``
        lifetime-aggregate endpoint EP-24.3 already ruled out — as returning
        **daily activity data grouped by model**, for the last 30 completed
        UTC days. Two things about this endpoint were **not**
        first-party-verified before this method was written, because this
        sandbox's network egress policy blocks direct access to
        ``openrouter.ai`` (confirmed via both a rejected ``curl`` CONNECT
        tunnel and a ``WebFetch`` 403 in the EP-26.0.1 research session):

        1. **Exact response field names** — this method's normalizer
           (``OpenRouterUsageNormalizer``) reads several plausible field-name
           variants defensively rather than assuming one unverified shape.
        2. **Whether the connection's standard, stored API key is
           sufficient**, or whether OpenRouter genuinely requires a more
           privileged "management key" (a materially different, higher-
           privilege credential this codebase does not store or request
           today — storing one without a deliberate product/security
           decision would violate this codebase's least-privilege posture,
           see CLAUDE.md's EP-26.0 Part 7).

        Rather than either (a) leaving this a permanent no-op — wasting a
        real, promising finding — or (b) silently requiring an unverified,
        more-privileged credential type, this method **attempts the real
        call with the connection's existing stored key** and degrades
        honestly: an ``AuthenticationError`` (401/403 — e.g. exactly the
        "this key lacks activity-read permission" case) is logged and
        skipped for that day rather than raised, so a connection whose key
        turns out to be insufficiently privileged still completes a healthy,
        honest, zero-additional-events sync — never a hard failure, and
        never fabricated data. **This is the one part of EP-26.0.1 that
        needs mandatory manual verification against a real OpenRouter
        account before being trusted as source-of-truth** — see CLAUDE.md's
        EP-26.0.1 "Known limitations."

        No range parameter exists on this endpoint (per the research above)
        — it accepts one ``date`` (UTC day) at a time, so this method issues
        one request per day across the requested window, clamped to
        OpenRouter's own documented 30-day retention window regardless of
        how far back ``start_date`` requests, so a stale checkpoint can
        never trigger an unbounded request loop.
        """
        from app.providers.models import UsagePage
        from app.usage.normalizer import OpenRouterUsageNormalizer

        try:
            key = self._resolve_key()
        except Exception as exc:
            # No credential configured at all — an honest, zero-event
            # outcome (matching every other adapter's "nothing to fetch
            # without a key" behavior) rather than propagating past this
            # adapter and failing the whole sync run.
            log.warning("openrouter_no_credential_for_usage_sync", error_type=type(exc).__name__)
            return UsagePage()

        normalizer = OpenRouterUsageNormalizer()

        earliest_allowed = (end_date - timedelta(days=_ACTIVITY_RETENTION_DAYS)).date()
        current = max(start_date.date(), earliest_allowed)
        last_day = end_date.date()

        from app.providers.models import NormalizedUsageEvent

        events: list[NormalizedUsageEvent] = []
        async with self._build_client(key) as client:
            while current <= last_day:
                try:
                    raw = await client.get("/api/v1/activity", params={"date": current.isoformat()})
                except AuthenticationError as exc:
                    log.warning(
                        "openrouter_activity_insufficient_permission",
                        date=current.isoformat(),
                        error=str(exc),
                    )
                    current += timedelta(days=1)
                    continue
                except Exception as exc:
                    log.warning(
                        "openrouter_activity_unavailable",
                        date=current.isoformat(),
                        error_type=type(exc).__name__,
                    )
                    current += timedelta(days=1)
                    continue

                items: list[dict[str, Any]] = raw.get("data", [])
                events.extend(normalizer.normalize(item) for item in items)
                current += timedelta(days=1)

        # /api/v1/activity has no cursor/offset pagination (per the research
        # above, it's one full day of grouped-by-model rows per request) —
        # every day in the window is already fetched by the loop above, so
        # there is nothing left to resume on a subsequent call.
        return UsagePage(events=events, next_cursor=None, has_more=False)

    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        from app.providers.info import ProviderInfo

        return ProviderInfo.from_capabilities(
            provider=self.provider_type.value,
            display_name=self._config.display_name,
            capabilities=_CAPABILITIES,
            health=health if health is not None else HealthStatus.UNKNOWN,
        )
