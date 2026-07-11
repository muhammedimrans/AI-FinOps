"""Google Gemini provider adapter — EP-22 (validation), EP-06
(catalog/capabilities), EP-26.0.2 (live model catalog, AI Studio platform
identity).

Scope: **Google AI Studio / the Gemini Developer API only.** Google Vertex
AI (a distinct product — OAuth/service-account auth, GCP-project-scoped,
richer Cloud Billing usage telemetry) is explicitly out of scope for this
adapter and is tracked as a future, separate integration — see CLAUDE.md's
EP-26.0 Part 1 for the full disambiguation between the two products and
EP-26.0.2's "Future Vertex AI roadmap" for what a Vertex adapter would add
on top of (not instead of) this one.

Authentication
--------------
API key travels as a ``?key=`` query parameter (Google's AI Studio / Gemini
API convention), not an Authorization header — see ``NullAuth`` in
``app.http.auth``; the key is passed via ``params`` on the request instead.

Live API calls
---------------
``GET /v1beta/models?key=<api_key>`` — the model discovery endpoint named in
the EP-22 spec, doubling as the credential-validation probe. As of
EP-26.0.2, this same endpoint also powers ``list_models()`` (a live,
paginated catalog call, replacing the old static 4-model list) — Google's
own response already carries ``displayName``, ``inputTokenLimit``,
``outputTokenLimit``, and ``supportedGenerationMethods`` per model, so no
second, separately-maintained enrichment table is needed the way OpenAI's
adapter uses one.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.http.auth import NullAuth
from app.http.client import ProviderHttpClient
from app.http.transport import HttpxTransport
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.credential import CredentialValidator, SecretResolver
from app.providers.interface import AIProvider
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
)

if TYPE_CHECKING:
    from app.providers.info import ProviderInfo
    from app.providers.models import UsagePage

log = structlog.get_logger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com"

# EP-26.0.2: safety bound on the live model-catalog pagination loop.
# Google's models.list documents a default pageSize of 50 and a hard
# server-side max of 1000 models per page; this many pages is already a
# generous ceiling relative to the real Gemini catalog's actual size, and
# exists purely so a misbehaving/looping nextPageToken can never spin
# forever rather than because it's expected to be reached in practice.
_MAX_MODEL_CATALOG_PAGES = 10

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=True,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=True,
    supports_fine_tuning=True,
    supports_function_calling=True,
    max_context_window=2000000,
    supported_model_ids=frozenset(
        {"gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-2.0-flash"}
    ),
)

# EP-26.0.2: this static list is now only a fallback, used by list_models()
# when the live GET /v1beta/models call fails or a credential isn't
# resolvable — the primary path calls the live catalog directly (see
# _model_from_live_catalog() below). Refreshed to the current-generation
# 2.5 line at the time of this EP (verified externally, not from training
# memory alone — CLAUDE.md's EP-26.0.2 section records the sources); kept
# intentionally small, since Google's real, fast-moving lineup is exactly
# why this method now prefers the live call over a hardcoded list at all.
_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        provider_type="google",
        context_window=1048576,
        max_output_tokens=65536,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.AUDIO,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        provider_type="google",
        context_window=1048576,
        max_output_tokens=65536,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.AUDIO,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash-Lite",
        provider_type="google",
        context_window=1048576,
        max_output_tokens=65536,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


def _capabilities_from_generation_methods(
    supported_methods: list[str], modality_hint: str
) -> frozenset[ModelCapabilityFlag]:
    """Map a live ``models.list`` item's ``supportedGenerationMethods`` (and
    a coarse name-based modality hint, since the Gemini API's model list
    does not expose a structured input/output-modality field the way
    OpenRouter's catalog does) into Costorah's provider-agnostic
    ``ModelCapabilityFlag`` set (EP-26.0.2).
    """
    methods = {m.lower() for m in supported_methods}
    caps: set[ModelCapabilityFlag] = set()
    if "streamgeneratecontent" in methods:
        caps.add(ModelCapabilityFlag.STREAMING)
    if "generatecontent" in methods or "streamgeneratecontent" in methods:
        # Every current Gemini generateContent-capable model supports
        # function/tool calling in the request schema; there is no
        # separate advertised flag for it in the models.list response.
        caps.add(ModelCapabilityFlag.TOOL_CALLING)
        caps.add(ModelCapabilityFlag.FUNCTION_CALLING)
    name = modality_hint.lower()
    if "vision" in name or "flash" in name or "pro" in name:
        # The 1.5+/2.x/3.x Gemini generateContent lines are natively
        # multimodal (image input) by default; embedding-only or
        # audio-only model IDs are excluded via the checks below.
        caps.add(ModelCapabilityFlag.VISION)
    if "embed" not in name and "imagen" not in name:
        caps.add(ModelCapabilityFlag.AUDIO)
    return frozenset(caps)


def _model_from_live_catalog(item: dict[str, Any]) -> ModelMetadata | None:
    """Map one item from Google's live ``GET /v1beta/models`` response into
    ``ModelMetadata`` (EP-26.0.2).

    Google's model ``name`` field is prefixed (``"models/gemini-2.5-pro"``);
    this strips the prefix to match every other adapter's bare-ID
    convention and this codebase's existing ``UsageCostRecord.model``/
    ``ModelPricing.model`` free-text columns (no schema change needed, per
    CLAUDE.md's EP-26.0 Part 4 finding). Returns ``None`` for entries with
    no generation-capable method at all (e.g. deprecated/internal aliases)
    — filtered out by the caller rather than surfaced as a broken model.
    """
    raw_name = str(item.get("name") or "")
    model_id = raw_name.removeprefix("models/")
    if not model_id:
        return None

    supported_methods = [str(m) for m in (item.get("supportedGenerationMethods") or [])]
    if not supported_methods:
        return None

    display_name = str(item.get("displayName") or model_id)
    input_limit = item.get("inputTokenLimit")
    output_limit = item.get("outputTokenLimit")
    is_deprecated = "deprecated" in display_name.lower() or "deprecated" in model_id.lower()

    return ModelMetadata(
        id=model_id,
        display_name=display_name,
        provider_type="google",
        context_window=int(input_limit) if input_limit else None,
        max_output_tokens=int(output_limit) if output_limit else None,
        capabilities=_capabilities_from_generation_methods(supported_methods, model_id),
        is_deprecated=is_deprecated,
    )


class GoogleProvider(AIProvider):
    """Google Gemini provider adapter — AI Studio / Gemini Developer API (EP-22, EP-26.0.2)."""

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
        return ProviderType.GOOGLE

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _build_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            base_url=self._config.base_url or _BASE_URL,
            auth=NullAuth(),
            provider_type="google",
            timeout=self._config.timeout_seconds,
            transport=self._transport,
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            from app.providers.errors import AuthenticationError

            raise AuthenticationError(
                "Google provider has no api_key_ref configured", provider_type="google"
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="google")

    async def verify_auth(self) -> bool:
        """Live GET /v1beta/models?key=<key> — raises AuthenticationError on 401/403."""
        key = self._resolve_key()
        CredentialValidator.validate_google_key(key)
        async with self._build_client() as client:
            await client.get("/v1beta/models", params={"key": key})
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
        """Live GET /v1beta/models catalog (EP-26.0.2), paginated via
        ``nextPageToken``, falling back to the small static ``_MODELS``
        list on any network/parse failure or a missing credential —
        matching the same "live call, static fallback only on error" shape
        ``OpenAIProvider.list_models()``/``OpenRouterProvider.list_models()``
        already established.

        A missing credential is not treated as fatal (unlike
        ``verify_auth()``, where it correctly is) — this preserves this
        method's pre-EP-26.0.2 contract of never requiring a resolved key
        just to return *some* model list, the same reasoning
        ``OpenRouterProvider.list_models()`` already applies for the same
        reason (EP-26.0.1).
        """
        try:
            key = self._resolve_key()
        except Exception as exc:
            log.warning("google_no_credential_for_model_catalog", error_type=type(exc).__name__)
            key = None

        models: list[ModelMetadata] = []
        page_token: str | None = None
        try:
            async with self._build_client() as client:
                for _ in range(_MAX_MODEL_CATALOG_PAGES):
                    params: dict[str, str] = {}
                    if key:
                        params["key"] = key
                    if page_token:
                        params["pageToken"] = page_token
                    data = await client.get("/v1beta/models", params=params)
                    raw_models: list[dict[str, Any]] = data.get("models", [])
                    for item in raw_models:
                        mapped = _model_from_live_catalog(item)
                        if mapped is not None:
                            models.append(mapped)
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
        except Exception as exc:
            log.warning("google_live_model_catalog_unavailable", error_type=type(exc).__name__)
            return list(_MODELS)

        return models or list(_MODELS)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> GoogleProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Google completion is implemented in EP-07")

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """No bulk usage-history endpoint exists for an AI-Studio API key.

        Google's per-request usage/cost data is only available through
        Cloud Billing export (BigQuery), which requires a GCP project and
        service-account credentials distinct from the Gemini API key this
        connection stores — there is no ``GET .../usage`` call this
        adapter's credential can make. Returning an honest empty page
        (rather than fabricating events) matches this codebase's standing
        "no fake functionality" rule; see CLAUDE.md's EP-24.3 section for
        the full per-provider accounting. The sync pipeline (checkpoint,
        retry, scheduler) still runs normally for this provider — it is
        simply the correct, honest outcome that runs 0 records every time.

        EP-26.0.2 re-verified this finding against current (July 2026)
        Google AI documentation before touching any code in this adapter —
        the AI Studio / Gemini Developer API surface still has no bulk,
        key-scoped usage-history endpoint. This is why EP-26.0.2 deliberately
        does **not** add a ``GeminiUsageNormalizer``/``GeminiUsageCollector``
        class: there is no real data source for either to wrap, and building
        one anyway — purely to satisfy a naming checklist — would be exactly
        the kind of dead code with nothing real behind it this codebase's
        no-fake-functionality rule exists to prevent. This capability
        remains gated on a future, separate Vertex AI Gemini integration
        (Cloud Billing Export, a GCP service-account credential — a
        different product and a different credential shape entirely, see
        this module's own top-of-file scope note and CLAUDE.md's EP-26.0.2
        "Future Vertex AI roadmap").
        """
        from app.providers.models import UsagePage

        return UsagePage()

    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        from app.providers.info import ProviderInfo

        return ProviderInfo.from_capabilities(
            provider=self.provider_type.value,
            display_name=self._config.display_name,
            capabilities=_CAPABILITIES,
            health=health if health is not None else HealthStatus.UNKNOWN,
        )
