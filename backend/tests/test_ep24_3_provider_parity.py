"""EP-24.3 test suite — Complete AI Provider Integrations (production parity).

Coverage targets:
- Every provider (openai, anthropic, grok, google, azure_openai, openrouter,
  ollama) is registered in ProviderFactory and constructible via
  build_provider_config — the shared config builder EP-22/EP-23.3 already
  established, unchanged by this EP.
- ProviderSyncService.sync_connection() no longer special-cases any
  provider type: every provider goes through the same
  UsageCollectionService.collect() call (EP-24.3's core change — removing
  the EP-23.3 skip/shortcut for "unsupported" providers).
- ProviderSyncService.sync_all_connections() syncs a mixed batch of
  providers uniformly, with no provider-specific filtering.
- SyncStatus.supports_usage_sync is informational only (UI messaging) and
  never gates whether a sync actually runs.
- Cost calculation (PricingEngine/ModelPricing) is provider-agnostic —
  works identically for a non-production provider's arbitrary
  provider/model string, and gracefully no-ops (no crash) when pricing is
  unconfigured, exactly as it already does for openai/anthropic.
- Budget evaluation (BudgetEvaluationService) accepts a provider-scoped
  budget for any provider string, not just openai/anthropic.
- Every adapter's get_usage() honestly returns an empty, non-crashing page
  (unchanged from EP-23.3/EP-06 — reconfirmed here as the parity baseline
  every provider must meet at minimum).

All tests are hermetic — no network calls, no real database, matching
every prior EP's test convention.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.budgets.service import BudgetEvaluationService
from app.models.budget import BudgetPeriod, BudgetScopeType
from app.models.provider_connection import ProviderType
from app.models.usage_collection_run import CollectionRunStatus
from app.providers.factory import ProviderFactory
from app.providers.validation import build_provider_config
from app.services.provider_sync_service import ProviderSyncService
from tests.conftest import make_provider_connection

if TYPE_CHECKING:
    from app.models.usage_collection_run import UsageCollectionRun

_ORG_ID = uuid.uuid4()

# The 7 providers with a real adapter + config builder (EP-06/EP-22/EP-24.3).
# ProviderType also has cohere/bedrock/mistral — valid *ingestion* sources
# (EP-16) with no adapter yet, deliberately out of this EP's scope (see
# ProviderType's own docstring).
_ALL_PROVIDER_TYPES = [
    ProviderType.OPENAI,
    ProviderType.ANTHROPIC,
    ProviderType.GROK,
    ProviderType.GOOGLE,
    ProviderType.AZURE_OPENAI,
    ProviderType.OPENROUTER,
    ProviderType.OLLAMA,
]
_NON_PRODUCTION_PROVIDERS = [
    p for p in _ALL_PROVIDER_TYPES if p.value not in ("openai", "anthropic")
]


def _build_config_kwargs(provider_type: ProviderType) -> dict[str, str | None]:
    """Azure OpenAI's config builder requires a base_url (the resource
    endpoint) — every other provider works with base_url=None."""
    if provider_type == ProviderType.AZURE_OPENAI:
        return {"api_key": "test-key", "base_url": "https://my-resource.openai.azure.com"}
    return {"api_key": "test-key", "base_url": None}


def _make_run(
    *, provider: str, status: CollectionRunStatus, connection_id: uuid.UUID
) -> UsageCollectionRun:
    from app.db.mixins import uuid7
    from app.models.usage_collection_run import UsageCollectionRun

    run = UsageCollectionRun()
    run.id = uuid7()
    run.organization_id = _ORG_ID
    run.provider_connection_id = connection_id
    run.provider = provider
    run.status = status
    run.started_at = datetime.now(UTC)
    run.completed_at = datetime.now(UTC)
    run.collection_start = datetime.now(UTC)
    run.collection_end = datetime.now(UTC)
    run.events_collected = 0
    run.events_failed = 0
    run.pages_fetched = 1
    run.collection_config = {}
    return run


# ══════════════════════════════════════════════════════════════════════════════
# Provider registry / config parity — every provider is constructible
# ══════════════════════════════════════════════════════════════════════════════


class TestProviderRegistryParity:
    def test_all_seven_providers_registered_in_default_registry(self) -> None:
        registry = ProviderFactory.build_default_registry()
        for pt in _ALL_PROVIDER_TYPES:
            assert registry.is_registered(pt)

    @pytest.mark.parametrize("provider_type", _ALL_PROVIDER_TYPES)
    def test_build_provider_config_succeeds_for_every_provider(
        self, provider_type: ProviderType
    ) -> None:
        config = build_provider_config(provider_type, **_build_config_kwargs(provider_type))
        assert config.provider_type == provider_type.value

    @pytest.mark.parametrize("provider_type", _ALL_PROVIDER_TYPES)
    def test_factory_constructs_adapter_for_every_provider(
        self, provider_type: ProviderType
    ) -> None:
        registry = ProviderFactory.build_default_registry()
        config = build_provider_config(provider_type, **_build_config_kwargs(provider_type))
        adapter = ProviderFactory(registry).create(config)
        assert adapter.provider_type == provider_type


# ══════════════════════════════════════════════════════════════════════════════
# get_usage() parity — every adapter returns a well-formed, empty page
# ══════════════════════════════════════════════════════════════════════════════


class TestGetUsageParityBaseline:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_type", _NON_PRODUCTION_PROVIDERS)
    async def test_non_production_adapters_return_empty_non_crashing_page(
        self, provider_type: ProviderType
    ) -> None:
        registry = ProviderFactory.build_default_registry()
        config = build_provider_config(provider_type, **_build_config_kwargs(provider_type))
        adapter = ProviderFactory(registry).create(config)
        try:
            page = await adapter.get_usage(
                datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
            )
            assert page.events == []
            assert page.has_more is False
        finally:
            await adapter.aclose()


# ══════════════════════════════════════════════════════════════════════════════
# ProviderSyncService — every provider goes through the same real pipeline
# ══════════════════════════════════════════════════════════════════════════════


class TestSyncPipelineParity:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_type", _ALL_PROVIDER_TYPES)
    async def test_every_provider_calls_collect_not_skipped(
        self, provider_type: ProviderType
    ) -> None:
        """EP-24.3's core behavioral change: no provider type takes a
        skip/shortcut anymore — sync_connection() always calls
        UsageCollectionService.collect()."""
        conn = make_provider_connection(
            org_id=_ORG_ID,
            provider_type=provider_type,
            encrypted_api_key="v1:ciphertext" if provider_type != ProviderType.OLLAMA else None,
            base_url=(
                "https://my-resource.openai.azure.com"
                if provider_type == ProviderType.AZURE_OPENAI
                else None
            ),
        )
        session = AsyncMock()
        mock_credentials = MagicMock()
        mock_credentials.decrypt.return_value = "plaintext-key"

        completed_run = _make_run(
            provider=provider_type.value,
            status=CollectionRunStatus.COMPLETED,
            connection_id=conn.id,
        )
        mock_collection = AsyncMock()
        mock_collection.collect.return_value = completed_run

        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None

        with patch(
            "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
            return_value=mock_checkpoint_repo,
        ):
            service = ProviderSyncService(
                session, credentials=mock_credentials, collection_service=mock_collection
            )
            run = await service.sync_connection(organization_id=_ORG_ID, connection=conn)

        assert run is completed_run
        mock_collection.collect.assert_awaited_once()
        assert mock_collection.collect.call_args.kwargs["provider"] == provider_type.value

    @pytest.mark.asyncio
    async def test_sync_all_connections_syncs_mixed_provider_batch_uniformly(self) -> None:
        """sync_all_connections() must never filter or special-case by
        provider type — a batch of openai/google/ollama connections are
        all synced through the identical code path."""
        connections = [
            make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI),
            make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.GOOGLE),
            make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OLLAMA),
        ]
        session = AsyncMock()

        page = MagicMock()
        page.items = connections
        mock_conn_repo = AsyncMock()
        mock_conn_repo.list_active_by_org.return_value = page

        service = ProviderSyncService(session)
        # sync_connection is exercised individually elsewhere; here we only
        # confirm sync_all_connections dispatches once per connection,
        # regardless of provider type.
        service.sync_connection = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _make_run(
                    provider=c.provider_type.value,
                    status=CollectionRunStatus.COMPLETED,
                    connection_id=c.id,
                )
                for c in connections
            ]
        )

        with patch(
            "app.services.provider_sync_service.ProviderConnectionRepository",
            return_value=mock_conn_repo,
        ):
            runs = await service.sync_all_connections(organization_id=_ORG_ID)

        assert len(runs) == 3
        assert service.sync_connection.await_count == 3


# ══════════════════════════════════════════════════════════════════════════════
# supports_usage_sync — informational only, never gates execution
# ══════════════════════════════════════════════════════════════════════════════


class TestSupportsUsageSyncIsInformationalOnly:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("provider_type", "expected"),
        [
            (ProviderType.OPENAI, True),
            (ProviderType.ANTHROPIC, True),
            (ProviderType.GOOGLE, False),
            (ProviderType.AZURE_OPENAI, False),
            (ProviderType.OPENROUTER, False),
            (ProviderType.GROK, False),
            (ProviderType.OLLAMA, False),
        ],
    )
    async def test_supports_usage_sync_reflects_known_usage_api_only(
        self, provider_type: ProviderType, expected: bool
    ) -> None:
        conn = make_provider_connection(org_id=_ORG_ID, provider_type=provider_type)
        session = AsyncMock()

        mock_run_repo = AsyncMock()
        mock_run_repo.get_latest_for_connection.return_value = None
        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None
        mock_event_repo = AsyncMock()
        mock_event_repo.get_totals_by_connection.return_value = {
            "total_records": 0,
            "total_tokens": 0,
        }
        mock_cost_repo = AsyncMock()
        mock_cost_repo.get_totals_by_connection.return_value = []

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageEventRepository",
                return_value=mock_event_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCostRecordRepository",
                return_value=mock_cost_repo,
            ),
        ):
            service = ProviderSyncService(session)
            status = await service.get_sync_status(organization_id=_ORG_ID, connection=conn)

        assert status.supports_usage_sync is expected


# ══════════════════════════════════════════════════════════════════════════════
# Cost calculation — provider-agnostic, graceful on unknown pricing
# ══════════════════════════════════════════════════════════════════════════════


class TestCostCalculationParity:
    @pytest.mark.asyncio
    async def test_pricing_engine_works_for_arbitrary_non_production_provider(self) -> None:
        from app.models.model_pricing import ModelPricing
        from app.pricing.engine import PricingEngine

        pricing = ModelPricing()
        pricing.id = uuid.uuid4()
        pricing.provider = "google"
        pricing.model = "gemini-1.5-pro"
        pricing.currency = "USD"
        pricing.prompt_token_price = Decimal("0.0000035")
        pricing.completion_token_price = Decimal("0.0000105")
        pricing.cached_token_price = None

        mock_repo = AsyncMock()
        engine = PricingEngine(mock_repo)
        result = engine.calculate_cost(pricing, prompt_tokens=1000, completion_tokens=500)

        assert result["currency"] == "USD"
        assert result["total_cost"] > 0

    @pytest.mark.asyncio
    async def test_unknown_pricing_for_non_production_provider_raises_not_found(self) -> None:
        """Graceful-handling contract: PricingEngine raises a typed,
        catchable error (not an unhandled exception) when no pricing row
        exists for a (provider, model) pair — the same behavior already
        exercised for openai/anthropic, now confirmed for a non-production
        provider too."""
        from app.pricing.engine import PricingEngine, PricingNotFoundError

        mock_repo = AsyncMock()
        mock_repo.get_for_date.return_value = None
        engine = PricingEngine(mock_repo)

        with pytest.raises(PricingNotFoundError):
            await engine.get_pricing_for_event(
                "openrouter", "meta-llama/llama-3.1-405b", date(2026, 1, 1)
            )


# ══════════════════════════════════════════════════════════════════════════════
# Budget evaluation — provider scope works for any provider string
# ══════════════════════════════════════════════════════════════════════════════


class TestBudgetEvaluationProviderParity:
    @pytest.mark.asyncio
    async def test_provider_scoped_budget_filters_by_arbitrary_provider_string(self) -> None:
        from app.models.budget import Budget

        session = AsyncMock()
        service = BudgetEvaluationService(session)
        mock_totals = AsyncMock(return_value=[])
        service._cost_records.get_totals_by_org = mock_totals  # type: ignore[method-assign]

        budget = Budget()
        budget.id = uuid.uuid4()
        budget.organization_id = _ORG_ID
        budget.name = "Grok Monthly Budget"
        budget.scope_type = BudgetScopeType.PROVIDER
        budget.scope_project_id = None
        budget.scope_provider = "grok"
        budget.scope_model = None
        budget.amount = Decimal("50.00")
        budget.currency = "USD"
        budget.period = BudgetPeriod.MONTHLY
        budget.custom_period_start = None
        budget.custom_period_end = None
        budget.threshold_percentages = [50.0, 90.0, 100.0]

        await service.evaluate_budget(budget, today=date(2026, 6, 15))

        call_kwargs = mock_totals.call_args.kwargs
        assert call_kwargs["provider"] == "grok"
        assert call_kwargs["project_id"] is None
        assert call_kwargs["model"] is None
