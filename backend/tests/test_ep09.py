"""EP-09 test suite — Cost & Analytics Engine.

Coverage targets:
- F-051: ModelPricing, UsageCostRecord, DailyCostSummary ORM models
- F-051: ModelPricingRepository — active/date-based pricing resolution
- F-051: UsageCostRecordRepository — upsert and aggregation queries
- F-054: DailyCostSummaryRepository — upsert and date-range queries
- F-051: PricingEngine — cost calculation, ROUND_HALF_UP, PricingNotFoundError
- F-056: PricingValidator — field validation, overlap detection
- F-053: AnalyticsService — all query methods
- F-054: AggregationService — daily summary building
- EP-09 API: pricing and analytics endpoints

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def _mock_org_membership() -> object:
    """Bypass the org-membership guard — authz behavior is tested in test_authz.py."""
    from unittest.mock import MagicMock

    from app.models.membership import Membership

    return MagicMock(spec=Membership)

# ── Import test subjects ───────────────────────────────────────────────────────

from app.models.model_pricing import ModelPricing
from app.models.usage_cost_record import UsageCostRecord
from app.models.daily_cost_summary import DailyCostSummary
from app.pricing.engine import CALCULATION_VERSION, PricingEngine, PricingNotFoundError
from app.pricing.validator import PricingValidationError, PricingValidator
from app.analytics.service import AnalyticsService

# ── Helpers ────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
_TODAY = date(2026, 6, 29)
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
_PRICING_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
_EVENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
_CONN_ID = uuid.UUID("00000000-0000-0000-0000-000000000005")


def _make_pricing(
    provider: str = "openai",
    model: str = "gpt-4",
    version: str = "v1",
    effective_from: date = date(2024, 1, 1),
    effective_to: date | None = None,
    prompt_price: Decimal = Decimal("0.00001"),
    completion_price: Decimal = Decimal("0.00003"),
    cached_price: Decimal | None = None,
    currency: str = "USD",
    is_active: bool = True,
) -> ModelPricing:
    """Build a ModelPricing ORM instance for testing."""
    pricing = ModelPricing()
    pricing.id = _PRICING_ID
    pricing.created_at = _NOW
    pricing.updated_at = _NOW
    pricing.provider = provider
    pricing.model = model
    pricing.version = version
    pricing.currency = currency
    pricing.effective_from = effective_from
    pricing.effective_to = effective_to
    pricing.prompt_token_price = prompt_price
    pricing.completion_token_price = completion_price
    pricing.cached_token_price = cached_price
    pricing.audio_token_price = None
    pricing.image_price = None
    pricing.embedding_price = None
    pricing.is_active = is_active
    pricing.notes = None
    return pricing


def _make_cost_record(
    org_id: uuid.UUID = _ORG_ID,
    event_id: uuid.UUID = _EVENT_ID,
    usage_date: date = _TODAY,
    total_cost: Decimal = Decimal("0.05"),
    total_tokens: int = 1000,
) -> UsageCostRecord:
    """Build a UsageCostRecord ORM instance for testing."""
    record = UsageCostRecord()
    record.id = uuid.uuid4()
    record.created_at = _NOW
    record.updated_at = _NOW
    record.usage_event_id = event_id
    record.organization_id = org_id
    record.project_id = _PROJECT_ID
    record.provider_connection_id = _CONN_ID
    record.model_pricing_id = _PRICING_ID
    record.provider = "openai"
    record.model = "gpt-4"
    record.currency = "USD"
    record.usage_date = usage_date
    record.prompt_tokens = 500
    record.completion_tokens = 500
    record.cached_tokens = None
    record.total_tokens = total_tokens
    record.prompt_cost = Decimal("0.005")
    record.completion_cost = Decimal("0.015")
    record.cached_cost = None
    record.total_cost = total_cost
    record.calculation_version = "1.0"
    return record


def _make_summary(
    org_id: uuid.UUID = _ORG_ID,
    summary_date: date = _TODAY,
    provider: str = "openai",
    model: str = "gpt-4",
    total_cost: Decimal = Decimal("1.00"),
) -> DailyCostSummary:
    """Build a DailyCostSummary ORM instance for testing."""
    summary = DailyCostSummary()
    summary.id = uuid.uuid4()
    summary.created_at = _NOW
    summary.updated_at = _NOW
    summary.organization_id = org_id
    summary.project_id = None
    summary.provider = provider
    summary.model = model
    summary.currency = "USD"
    summary.summary_date = summary_date
    summary.total_prompt_tokens = 500
    summary.total_completion_tokens = 500
    summary.total_cached_tokens = None
    summary.total_tokens = 1000
    summary.total_requests = 10
    summary.total_cost = total_cost
    summary.total_prompt_cost = Decimal("0.005")
    summary.total_completion_cost = Decimal("0.015")
    summary.total_cached_cost = None
    summary.event_count = 10
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# ModelPricing Model Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestModelPricing:
    """Tests for the ModelPricing ORM model."""

    def test_tablename(self) -> None:
        assert ModelPricing.__tablename__ == "model_pricing"

    def test_external_id_prefix(self) -> None:
        assert ModelPricing._external_id_prefix == "mpr"

    def test_external_id_property(self) -> None:
        pricing = _make_pricing()
        assert pricing.external_id.startswith("mpr_")
        assert pricing.external_id == f"mpr_{pricing.id.hex}"

    def test_decimal_fields_are_decimal(self) -> None:
        pricing = _make_pricing(
            prompt_price=Decimal("0.00001"),
            completion_price=Decimal("0.00003"),
        )
        assert isinstance(pricing.prompt_token_price, Decimal)
        assert isinstance(pricing.completion_token_price, Decimal)

    def test_optional_fields_default_none(self) -> None:
        pricing = _make_pricing()
        assert pricing.cached_token_price is None
        assert pricing.audio_token_price is None
        assert pricing.image_price is None
        assert pricing.embedding_price is None
        assert pricing.effective_to is None
        assert pricing.notes is None

    def test_is_active_default(self) -> None:
        pricing = _make_pricing()
        assert pricing.is_active is True

    def test_currency_field(self) -> None:
        pricing = _make_pricing(currency="EUR")
        assert pricing.currency == "EUR"

    def test_version_field(self) -> None:
        pricing = _make_pricing(version="2024-06-01")
        assert pricing.version == "2024-06-01"

    def test_effective_date_fields(self) -> None:
        pricing = _make_pricing(
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        assert pricing.effective_from == date(2024, 1, 1)
        assert pricing.effective_to == date(2024, 12, 31)

    def test_with_cached_price(self) -> None:
        pricing = _make_pricing(cached_price=Decimal("0.000005"))
        assert pricing.cached_token_price == Decimal("0.000005")

    def test_zero_prices_allowed(self) -> None:
        pricing = _make_pricing(
            prompt_price=Decimal(0),
            completion_price=Decimal(0),
        )
        assert pricing.prompt_token_price == Decimal(0)
        assert pricing.completion_token_price == Decimal(0)

    def test_repr(self) -> None:
        pricing = _make_pricing()
        repr_str = repr(pricing)
        assert "ModelPricing" in repr_str


# ══════════════════════════════════════════════════════════════════════════════
# UsageCostRecord Model Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageCostRecord:
    """Tests for the UsageCostRecord ORM model."""

    def test_tablename(self) -> None:
        assert UsageCostRecord.__tablename__ == "usage_cost_records"

    def test_external_id_prefix(self) -> None:
        assert UsageCostRecord._external_id_prefix == "ucr"

    def test_cost_fields_are_decimal(self) -> None:
        record = _make_cost_record()
        assert isinstance(record.prompt_cost, Decimal)
        assert isinstance(record.completion_cost, Decimal)
        assert isinstance(record.total_cost, Decimal)

    def test_optional_cached_fields(self) -> None:
        record = _make_cost_record()
        assert record.cached_tokens is None
        assert record.cached_cost is None

    def test_usage_date_is_date(self) -> None:
        record = _make_cost_record()
        assert isinstance(record.usage_date, date)

    def test_calculation_version(self) -> None:
        record = _make_cost_record()
        assert record.calculation_version == "1.0"

    def test_fk_fields(self) -> None:
        record = _make_cost_record()
        assert record.usage_event_id == _EVENT_ID
        assert record.organization_id == _ORG_ID
        assert record.project_id == _PROJECT_ID

    def test_external_id_property(self) -> None:
        record = _make_cost_record()
        assert record.external_id.startswith("ucr_")

    def test_token_counts(self) -> None:
        record = _make_cost_record(total_tokens=2000)
        assert record.prompt_tokens == 500
        assert record.completion_tokens == 500
        assert record.total_tokens == 2000


# ══════════════════════════════════════════════════════════════════════════════
# DailyCostSummary Model Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDailyCostSummary:
    """Tests for the DailyCostSummary ORM model."""

    def test_tablename(self) -> None:
        assert DailyCostSummary.__tablename__ == "daily_cost_summaries"

    def test_external_id_prefix(self) -> None:
        assert DailyCostSummary._external_id_prefix == "dcs"

    def test_cost_fields_are_decimal(self) -> None:
        summary = _make_summary()
        assert isinstance(summary.total_cost, Decimal)
        assert isinstance(summary.total_prompt_cost, Decimal)
        assert isinstance(summary.total_completion_cost, Decimal)

    def test_big_integer_token_fields(self) -> None:
        summary = _make_summary()
        assert isinstance(summary.total_prompt_tokens, int)
        assert isinstance(summary.total_completion_tokens, int)
        assert isinstance(summary.total_tokens, int)

    def test_summary_date_is_date(self) -> None:
        summary = _make_summary()
        assert isinstance(summary.summary_date, date)

    def test_project_id_nullable(self) -> None:
        summary = _make_summary()
        assert summary.project_id is None

    def test_with_project_id(self) -> None:
        summary = _make_summary()
        summary.project_id = _PROJECT_ID
        assert summary.project_id == _PROJECT_ID

    def test_event_count(self) -> None:
        summary = _make_summary()
        assert summary.event_count == 10

    def test_total_requests(self) -> None:
        summary = _make_summary()
        assert summary.total_requests == 10

    def test_optional_cached_fields(self) -> None:
        summary = _make_summary()
        assert summary.total_cached_tokens is None
        assert summary.total_cached_cost is None

    def test_external_id_property(self) -> None:
        summary = _make_summary()
        assert summary.external_id.startswith("dcs_")


# ══════════════════════════════════════════════════════════════════════════════
# ModelPricingRepository Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestModelPricingRepository:
    """Tests for ModelPricingRepository."""

    def _make_repo(self) -> Any:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        session = AsyncMock()
        return ModelPricingRepository(session), session

    @pytest.mark.asyncio
    async def test_get_active_for_model_returns_pricing(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        pricing = _make_pricing()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pricing
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_active_for_model("openai", "gpt-4")
        assert result is pricing

    @pytest.mark.asyncio
    async def test_get_active_for_model_not_found(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_active_for_model("openai", "unknown-model")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_for_date_returns_pricing(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        pricing = _make_pricing(effective_from=date(2024, 1, 1))
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pricing
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_for_date("openai", "gpt-4", date(2025, 1, 1))
        assert result is pricing

    @pytest.mark.asyncio
    async def test_get_for_date_not_found(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_for_date("openai", "gpt-4", date(2020, 1, 1))
        assert result is None

    @pytest.mark.asyncio
    async def test_list_for_provider(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        pricings = [_make_pricing(), _make_pricing(model="gpt-3.5-turbo")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = pricings
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.list_for_provider("openai")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_for_model(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        pricings = [_make_pricing(version="v1"), _make_pricing(version="v2")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = pricings
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.list_for_model("openai", "gpt-4")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_version(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        pricing = _make_pricing(version="v2")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pricing
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_version("openai", "gpt-4", "v2")
        assert result is pricing
        assert result.version == "v2"

    @pytest.mark.asyncio
    async def test_get_by_version_not_found(self) -> None:
        from app.repositories.model_pricing_repository import ModelPricingRepository
        repo, session = self._make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_version("openai", "gpt-4", "nonexistent")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# UsageCostRecordRepository Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageCostRecordRepository:
    """Tests for UsageCostRecordRepository."""

    def _make_repo(self) -> Any:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        session = AsyncMock()
        return UsageCostRecordRepository(session), session

    @pytest.mark.asyncio
    async def test_get_by_event_found(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()
        record = _make_cost_record()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_event(_EVENT_ID)
        assert result is record

    @pytest.mark.asyncio
    async def test_get_by_event_not_found(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_event(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_calls_execute(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()
        record = _make_cost_record()

        # First execute: the upsert INSERT ON CONFLICT
        # Second execute: the SELECT to return the persisted record
        mock_upsert_result = MagicMock()
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = record
        session.execute = AsyncMock(side_effect=[mock_upsert_result, mock_select_result])
        session.flush = AsyncMock()

        result = await repo.upsert(record)
        assert result is record
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_totals_by_org_returns_list(self) -> None:
        """get_totals_by_org returns list[dict], one entry per currency (RH-01)."""
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_row = MagicMock()
        mock_row.currency = "USD"
        mock_row.total_cost = Decimal("100.00")
        mock_row.total_tokens = 5000
        mock_row.total_prompt_tokens = 2500
        mock_row.total_completion_tokens = 2500
        mock_row.record_count = 10

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_totals_by_org(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["currency"] == "USD"
        assert result[0]["total_cost"] == Decimal("100.00")
        assert result[0]["total_tokens"] == 5000
        assert result[0]["record_count"] == 10

    @pytest.mark.asyncio
    async def test_get_totals_by_org_multi_currency_separate(self) -> None:
        """RH-01: USD and EUR totals are returned as separate list entries, never summed."""
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_usd = MagicMock()
        mock_usd.currency = "USD"
        mock_usd.total_cost = Decimal("123.45")
        mock_usd.total_tokens = 1000
        mock_usd.total_prompt_tokens = 500
        mock_usd.total_completion_tokens = 500
        mock_usd.record_count = 5

        mock_eur = MagicMock()
        mock_eur.currency = "EUR"
        mock_eur.total_cost = Decimal("50.00")
        mock_eur.total_tokens = 500
        mock_eur.total_prompt_tokens = 250
        mock_eur.total_completion_tokens = 250
        mock_eur.record_count = 2

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_usd, mock_eur]
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_totals_by_org(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(result) == 2

        currencies = {r["currency"] for r in result}
        assert currencies == {"USD", "EUR"}

        usd = next(r for r in result if r["currency"] == "USD")
        eur = next(r for r in result if r["currency"] == "EUR")

        # USD total must NOT include EUR amount
        assert usd["total_cost"] == Decimal("123.45")
        assert eur["total_cost"] == Decimal("50.00")
        # They are separate — never mixed
        assert usd["total_cost"] != usd["total_cost"] + eur["total_cost"]

    @pytest.mark.asyncio
    async def test_get_totals_by_org_empty_returns_empty_list(self) -> None:
        """RH-01: No records → empty list, not an error."""
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_totals_by_org(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_totals_by_provider(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_row = MagicMock()
        mock_row.provider = "openai"
        mock_row.currency = "USD"
        mock_row.total_cost = Decimal("50.00")
        mock_row.total_prompt_cost = Decimal("20.00")
        mock_row.total_completion_cost = Decimal("30.00")
        mock_row.total_tokens = 2000
        mock_row.total_prompt_tokens = 1000
        mock_row.total_completion_tokens = 1000
        mock_row.record_count = 5

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute = AsyncMock(return_value=mock_result)

        results = await repo.get_totals_by_provider(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(results) == 1
        assert results[0]["provider"] == "openai"
        assert results[0]["total_cost"] == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_get_totals_by_model(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_row = MagicMock()
        mock_row.provider = "openai"
        mock_row.model = "gpt-4"
        mock_row.currency = "USD"
        mock_row.total_cost = Decimal("50.00")
        mock_row.total_prompt_cost = Decimal("20.00")
        mock_row.total_completion_cost = Decimal("30.00")
        mock_row.total_tokens = 2000
        mock_row.total_prompt_tokens = 1000
        mock_row.total_completion_tokens = 1000
        mock_row.record_count = 5

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute = AsyncMock(return_value=mock_result)

        results = await repo.get_totals_by_model(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(results) == 1
        assert results[0]["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_get_totals_by_project(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_row = MagicMock()
        mock_row.project_id = _PROJECT_ID
        mock_row.currency = "USD"
        mock_row.total_cost = Decimal("25.00")
        mock_row.total_tokens = 1000
        mock_row.record_count = 3

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute = AsyncMock(return_value=mock_result)

        results = await repo.get_totals_by_project(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(results) == 1
        assert results[0]["project_id"] == _PROJECT_ID

    @pytest.mark.asyncio
    async def test_get_daily_trend(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        repo, session = self._make_repo()

        mock_row = MagicMock()
        mock_row.usage_date = date(2026, 6, 1)
        mock_row.currency = "USD"
        mock_row.total_cost = Decimal("10.00")
        mock_row.total_prompt_cost = Decimal("4.00")
        mock_row.total_completion_cost = Decimal("6.00")
        mock_row.total_tokens = 500
        mock_row.record_count = 2

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute = AsyncMock(return_value=mock_result)

        results = await repo.get_daily_trend(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))
        assert len(results) == 1
        assert results[0]["usage_date"] == date(2026, 6, 1)
        assert results[0]["total_cost"] == Decimal("10.00")


# ══════════════════════════════════════════════════════════════════════════════
# DailyCostSummaryRepository Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDailyCostSummaryRepository:
    """Tests for DailyCostSummaryRepository."""

    def _make_repo(self) -> Any:
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        session = AsyncMock()
        return DailyCostSummaryRepository(session), session

    @pytest.mark.asyncio
    async def test_upsert_calls_execute(self) -> None:
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        repo, session = self._make_repo()
        summary = _make_summary()

        mock_upsert_result = MagicMock()
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = summary
        session.execute = AsyncMock(side_effect=[mock_upsert_result, mock_select_result])
        session.flush = AsyncMock()

        result = await repo.upsert(summary)
        assert result is summary
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_upsert_returns_original_on_miss(self) -> None:
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        repo, session = self._make_repo()
        summary = _make_summary()

        mock_upsert_result = MagicMock()
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = None  # not found on SELECT
        session.execute = AsyncMock(side_effect=[mock_upsert_result, mock_select_result])
        session.flush = AsyncMock()

        result = await repo.upsert(summary)
        # Falls back to original summary
        assert result is summary

    @pytest.mark.asyncio
    async def test_get_for_date_range(self) -> None:
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        repo, session = self._make_repo()
        summaries = [_make_summary(summary_date=date(2026, 6, 1))]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = summaries
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_for_date_range(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_by_provider(self) -> None:
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        repo, session = self._make_repo()
        summaries = [_make_summary(provider="anthropic")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = summaries
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_provider(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))
        assert len(result) == 1
        assert result[0].provider == "anthropic"

    @pytest.mark.asyncio
    async def test_get_by_model(self) -> None:
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        repo, session = self._make_repo()
        summaries = [_make_summary(model="claude-3-5-sonnet")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = summaries
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_model(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))
        assert len(result) == 1
        assert result[0].model == "claude-3-5-sonnet"


# ══════════════════════════════════════════════════════════════════════════════
# PricingEngine Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPricingEngine:
    """Tests for PricingEngine — deterministic cost calculation."""

    def _make_engine(self, pricing: ModelPricing | None = None) -> PricingEngine:
        mock_repo = AsyncMock()
        mock_repo.get_for_date = AsyncMock(return_value=pricing)
        return PricingEngine(mock_repo)

    @pytest.mark.asyncio
    async def test_get_pricing_for_event_found(self) -> None:
        pricing = _make_pricing()
        engine = self._make_engine(pricing)
        result = await engine.get_pricing_for_event("openai", "gpt-4", _TODAY)
        assert result is pricing

    @pytest.mark.asyncio
    async def test_get_pricing_for_event_not_found_raises(self) -> None:
        engine = self._make_engine(None)
        with pytest.raises(PricingNotFoundError) as exc_info:
            await engine.get_pricing_for_event("openai", "gpt-4-nonexistent", _TODAY)
        assert "openai/gpt-4-nonexistent" in str(exc_info.value)

    def test_calculate_cost_basic(self) -> None:
        pricing = _make_pricing(
            prompt_price=Decimal("0.00001"),
            completion_price=Decimal("0.00003"),
        )
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(
            pricing,
            prompt_tokens=1000,
            completion_tokens=500,
        )
        # 1000 * 0.00001 = 0.01
        assert result["prompt_cost"] == Decimal("0.01000000")
        # 500 * 0.00003 = 0.015
        assert result["completion_cost"] == Decimal("0.01500000")
        # total = 0.025
        assert result["total_cost"] == Decimal("0.02500000")
        assert result["currency"] == "USD"
        assert result["calculation_version"] == CALCULATION_VERSION

    def test_calculate_cost_returns_decimal_not_float(self) -> None:
        pricing = _make_pricing()
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(pricing, prompt_tokens=100, completion_tokens=100)
        assert isinstance(result["prompt_cost"], Decimal)
        assert isinstance(result["completion_cost"], Decimal)
        assert isinstance(result["total_cost"], Decimal)

    def test_calculate_cost_with_cached_tokens(self) -> None:
        pricing = _make_pricing(
            prompt_price=Decimal("0.00001"),
            completion_price=Decimal("0.00003"),
            cached_price=Decimal("0.000005"),
        )
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(
            pricing,
            prompt_tokens=1000,
            completion_tokens=500,
            cached_tokens=200,
        )
        # 200 * 0.000005 = 0.001
        assert result["cached_cost"] == Decimal("0.00100000")
        # total = 0.01 + 0.015 + 0.001 = 0.026
        assert result["total_cost"] == Decimal("0.02600000")

    def test_calculate_cost_cached_none_when_no_pricing(self) -> None:
        pricing = _make_pricing(cached_price=None)
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(
            pricing,
            prompt_tokens=100,
            completion_tokens=100,
            cached_tokens=50,  # tokens provided but no pricing
        )
        assert result["cached_cost"] is None

    def test_calculate_cost_no_cached_tokens(self) -> None:
        pricing = _make_pricing(cached_price=Decimal("0.000005"))
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(
            pricing,
            prompt_tokens=100,
            completion_tokens=100,
            cached_tokens=None,
        )
        assert result["cached_cost"] is None

    def test_calculate_cost_zero_tokens(self) -> None:
        pricing = _make_pricing()
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(pricing, prompt_tokens=0, completion_tokens=0)
        assert result["prompt_cost"] == Decimal("0.00000000")
        assert result["completion_cost"] == Decimal("0.00000000")
        assert result["total_cost"] == Decimal("0.00000000")

    def test_calculate_cost_precision_8dp(self) -> None:
        """Verify all results are quantized to exactly 8 decimal places."""
        pricing = _make_pricing(
            prompt_price=Decimal("0.00001"),
            completion_price=Decimal("0.00003"),
        )
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(
            pricing,
            prompt_tokens=100,
            completion_tokens=100,
        )
        # Results should have exactly 8 decimal places via quantize
        quant = Decimal("0.00000001")
        assert result["prompt_cost"] == (Decimal(100) * Decimal("0.00001")).quantize(quant)
        assert result["completion_cost"] == (Decimal(100) * Decimal("0.00003")).quantize(quant)
        # Verify they are Decimal instances with the right exponent
        assert result["prompt_cost"].as_tuple().exponent == -8
        assert result["completion_cost"].as_tuple().exponent == -8

    def test_calculate_cost_round_half_up(self) -> None:
        """Verify ROUND_HALF_UP rounding behavior."""
        # 3 tokens * 0.0000001 = 0.0000003 → 0.00000030
        pricing = _make_pricing(
            prompt_price=Decimal("0.0000001"),
            completion_price=Decimal("0"),
        )
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(pricing, prompt_tokens=3, completion_tokens=0)
        assert result["prompt_cost"] == Decimal("0.00000030")

    def test_calculate_cost_model_pricing_id(self) -> None:
        pricing = _make_pricing()
        engine = self._make_engine(pricing)
        result = engine.calculate_cost(pricing, prompt_tokens=100, completion_tokens=100)
        assert result["model_pricing_id"] == _PRICING_ID

    @pytest.mark.asyncio
    async def test_calculate_event_cost(self) -> None:
        """Test convenience method calculates from a UsageEvent-like object."""
        pricing = _make_pricing(
            prompt_price=Decimal("0.00001"),
            completion_price=Decimal("0.00003"),
        )
        engine = self._make_engine(pricing)

        # Mock UsageEvent-like object
        event = MagicMock()
        event.provider = "openai"
        event.model = "gpt-4"
        event.prompt_tokens = 1000
        event.completion_tokens = 500
        event.cached_tokens = None

        result = await engine.calculate_event_cost(event, _TODAY)
        assert result["total_cost"] == Decimal("0.02500000")

    @pytest.mark.asyncio
    async def test_calculate_event_cost_pricing_not_found(self) -> None:
        engine = self._make_engine(None)

        event = MagicMock()
        event.provider = "unknown"
        event.model = "unknown-model"
        event.prompt_tokens = 100
        event.completion_tokens = 100
        event.cached_tokens = None

        with pytest.raises(PricingNotFoundError):
            await engine.calculate_event_cost(event, _TODAY)

    def test_calculation_version_constant(self) -> None:
        assert CALCULATION_VERSION == "1.0"


# ══════════════════════════════════════════════════════════════════════════════
# PricingValidator Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPricingValidator:
    """Tests for PricingValidator — field validation and overlap detection."""

    def _make_validator(self) -> PricingValidator:
        return PricingValidator()

    def test_validate_new_pricing_valid(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        # Should not raise
        validator.validate_new_pricing(pricing)

    def test_validate_empty_provider_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.provider = ""
        with pytest.raises(PricingValidationError, match="provider"):
            validator.validate_new_pricing(pricing)

    def test_validate_empty_model_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.model = ""
        with pytest.raises(PricingValidationError, match="model"):
            validator.validate_new_pricing(pricing)

    def test_validate_empty_version_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.version = ""
        with pytest.raises(PricingValidationError, match="version"):
            validator.validate_new_pricing(pricing)

    def test_validate_empty_currency_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.currency = ""
        with pytest.raises(PricingValidationError, match="currency"):
            validator.validate_new_pricing(pricing)

    def test_validate_none_effective_from_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.effective_from = None  # type: ignore[assignment]
        with pytest.raises(PricingValidationError, match="effective_from"):
            validator.validate_new_pricing(pricing)

    def test_validate_effective_to_before_from_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(
            effective_from=date(2024, 6, 1),
            effective_to=date(2024, 1, 1),
        )
        with pytest.raises(PricingValidationError, match="effective_to"):
            validator.validate_new_pricing(pricing)

    def test_validate_effective_to_equal_from_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 1, 1),
        )
        with pytest.raises(PricingValidationError, match="effective_to"):
            validator.validate_new_pricing(pricing)

    def test_validate_negative_prompt_price_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(prompt_price=Decimal("-0.001"))
        with pytest.raises(PricingValidationError, match="prompt_token_price"):
            validator.validate_new_pricing(pricing)

    def test_validate_negative_completion_price_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(completion_price=Decimal("-0.001"))
        with pytest.raises(PricingValidationError, match="completion_token_price"):
            validator.validate_new_pricing(pricing)

    def test_validate_negative_cached_price_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(cached_price=Decimal("-0.001"))
        with pytest.raises(PricingValidationError, match="cached_token_price"):
            validator.validate_new_pricing(pricing)

    def test_validate_negative_audio_price_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.audio_token_price = Decimal("-0.001")
        with pytest.raises(PricingValidationError, match="audio_token_price"):
            validator.validate_new_pricing(pricing)

    def test_validate_negative_image_price_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.image_price = Decimal("-0.001")
        with pytest.raises(PricingValidationError, match="image_price"):
            validator.validate_new_pricing(pricing)

    def test_validate_negative_embedding_price_raises(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        pricing.embedding_price = Decimal("-0.001")
        with pytest.raises(PricingValidationError, match="embedding_price"):
            validator.validate_new_pricing(pricing)

    def test_validate_zero_prices_valid(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(
            prompt_price=Decimal(0),
            completion_price=Decimal(0),
        )
        # Should not raise — zero is valid
        validator.validate_new_pricing(pricing)

    def test_validate_with_all_optional_fields(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(cached_price=Decimal("0.000005"))
        pricing.audio_token_price = Decimal("0.00001")
        pricing.image_price = Decimal("0.001")
        pricing.embedding_price = Decimal("0.0001")
        pricing.effective_to = date(2025, 12, 31)
        # Should not raise
        validator.validate_new_pricing(pricing)

    @pytest.mark.asyncio
    async def test_validate_no_overlap_no_existing(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing()
        mock_repo = AsyncMock()
        mock_repo.list_for_model = AsyncMock(return_value=[])
        # Should not raise
        await validator.validate_no_overlap(mock_repo, pricing)

    @pytest.mark.asyncio
    async def test_validate_no_overlap_with_overlap_raises(self) -> None:
        validator = self._make_validator()

        # Existing: 2024-01-01 to None (open-ended)
        existing = _make_pricing(
            version="v1",
            effective_from=date(2024, 1, 1),
            effective_to=None,
        )
        existing.id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        # New: 2025-01-01 to None — overlaps with existing
        new_pricing = _make_pricing(
            version="v2",
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )
        new_pricing.id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        mock_repo = AsyncMock()
        mock_repo.list_for_model = AsyncMock(return_value=[existing])

        with pytest.raises(PricingValidationError, match="overlap"):
            await validator.validate_no_overlap(mock_repo, new_pricing)

    @pytest.mark.asyncio
    async def test_validate_no_overlap_adjacent_ranges_ok(self) -> None:
        validator = self._make_validator()

        # Existing: 2024-01-01 to 2024-12-31
        existing = _make_pricing(
            version="v1",
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        existing.id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        # New: 2025-01-01 onwards — no overlap
        new_pricing = _make_pricing(
            version="v2",
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )
        new_pricing.id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        mock_repo = AsyncMock()
        mock_repo.list_for_model = AsyncMock(return_value=[existing])

        # Should not raise
        await validator.validate_no_overlap(mock_repo, new_pricing)

    @pytest.mark.asyncio
    async def test_validate_no_overlap_skips_same_id(self) -> None:
        validator = self._make_validator()
        pricing = _make_pricing(
            effective_from=date(2024, 1, 1),
            effective_to=None,
        )
        # Same record listed — should not flag itself as overlap
        mock_repo = AsyncMock()
        mock_repo.list_for_model = AsyncMock(return_value=[pricing])

        # Should not raise
        await validator.validate_no_overlap(mock_repo, pricing)


# ══════════════════════════════════════════════════════════════════════════════
# AnalyticsService Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAnalyticsService:
    """Tests for AnalyticsService — read-only analytics methods."""

    def _make_service(
        self,
        org_totals: list | None = None,
        provider_totals: list | None = None,
        model_totals: list | None = None,
        project_totals: list | None = None,
        daily_trend: list | None = None,
    ) -> AnalyticsService:
        cost_repo = AsyncMock()
        daily_repo = AsyncMock()

        # Default: single-currency USD totals (list of one entry — RH-01 shape)
        default_org_totals = [
            {
                "currency": "USD",
                "total_cost": Decimal("100.00"),
                "total_tokens": 5000,
                "total_prompt_tokens": 2500,
                "total_completion_tokens": 2500,
                "record_count": 10,
            }
        ]
        cost_repo.get_totals_by_org = AsyncMock(return_value=org_totals or default_org_totals)
        cost_repo.get_totals_by_provider = AsyncMock(return_value=provider_totals or [])
        cost_repo.get_totals_by_model = AsyncMock(return_value=model_totals or [])
        cost_repo.get_totals_by_project = AsyncMock(return_value=project_totals or [])
        cost_repo.get_daily_trend = AsyncMock(return_value=daily_trend or [])

        return AnalyticsService(cost_repo, daily_repo)

    @pytest.mark.asyncio
    async def test_get_usage_summary(self) -> None:
        service = self._make_service()
        result = await service.get_usage_summary(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert result["total_tokens"] == 5000
        assert result["total_requests"] == 10
        assert result["organization_id"] == str(_ORG_ID)

    @pytest.mark.asyncio
    async def test_get_cost_summary(self) -> None:
        service = self._make_service()
        result = await service.get_cost_summary(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        # RH-01: cost_by_currency is a list
        assert "cost_by_currency" in result
        assert len(result["cost_by_currency"]) == 1
        assert result["cost_by_currency"][0]["currency"] == "USD"
        assert result["total_cost"] == Decimal("100.00")
        assert result["record_count"] == 10

    @pytest.mark.asyncio
    async def test_get_cost_summary_multi_currency(self) -> None:
        """RH-01: Cost summary returns separate entries per currency."""
        multi_currency_totals = [
            {
                "currency": "USD",
                "total_cost": Decimal("200.00"),
                "total_tokens": 8000,
                "total_prompt_tokens": 4000,
                "total_completion_tokens": 4000,
                "record_count": 15,
            },
            {
                "currency": "EUR",
                "total_cost": Decimal("75.00"),
                "total_tokens": 3000,
                "total_prompt_tokens": 1500,
                "total_completion_tokens": 1500,
                "record_count": 5,
            },
        ]
        service = self._make_service(org_totals=multi_currency_totals)
        result = await service.get_cost_summary(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(result["cost_by_currency"]) == 2
        currencies = {c["currency"] for c in result["cost_by_currency"]}
        assert currencies == {"USD", "EUR"}
        # total_cost convenience field is the first currency (USD)
        assert result["total_cost"] == Decimal("200.00")
        # record_count is the sum across both currencies
        assert result["record_count"] == 20

    @pytest.mark.asyncio
    async def test_get_provider_breakdown(self) -> None:
        provider_data = [
            {
                "provider": "openai",
                "currency": "USD",
                "total_cost": Decimal("80.00"),
                "total_prompt_cost": Decimal("30.00"),
                "total_completion_cost": Decimal("50.00"),
                "total_tokens": 4000,
                "total_prompt_tokens": 2000,
                "total_completion_tokens": 2000,
                "record_count": 8,
            }
        ]
        service = self._make_service(provider_totals=provider_data)
        result = await service.get_provider_breakdown(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(result) == 1
        assert result[0]["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_get_model_breakdown(self) -> None:
        model_data = [
            {
                "provider": "openai",
                "model": "gpt-4",
                "currency": "USD",
                "total_cost": Decimal("80.00"),
                "total_prompt_cost": Decimal("30.00"),
                "total_completion_cost": Decimal("50.00"),
                "total_tokens": 4000,
                "total_prompt_tokens": 2000,
                "total_completion_tokens": 2000,
                "record_count": 8,
            }
        ]
        service = self._make_service(model_totals=model_data)
        result = await service.get_model_breakdown(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(result) == 1
        assert result[0]["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_get_project_breakdown(self) -> None:
        project_data = [
            {
                "project_id": _PROJECT_ID,
                "currency": "USD",
                "total_cost": Decimal("50.00"),
                "total_tokens": 2500,
                "record_count": 5,
            }
        ]
        service = self._make_service(project_totals=project_data)
        result = await service.get_project_breakdown(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert len(result) == 1
        assert result[0]["project_id"] == _PROJECT_ID

    @pytest.mark.asyncio
    async def test_get_daily_trend(self) -> None:
        trend_data = [
            {
                "usage_date": date(2026, 6, 1),
                "currency": "USD",
                "total_cost": Decimal("10.00"),
                "total_prompt_cost": Decimal("4.00"),
                "total_completion_cost": Decimal("6.00"),
                "total_tokens": 500,
                "record_count": 2,
            }
        ]
        service = self._make_service(daily_trend=trend_data)
        result = await service.get_daily_trend(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))
        assert len(result) == 1
        assert result[0]["usage_date"] == date(2026, 6, 1)

    @pytest.mark.asyncio
    async def test_get_top_models_limit(self) -> None:
        """RH-05: SQL LIMIT is applied in the repository, not Python-side slicing."""
        # Mock returns exactly limit items (simulating SQL LIMIT applied in DB)
        model_data = [
            {
                "provider": "openai",
                "model": f"model-{i}",
                "currency": "USD",
                "total_cost": Decimal(str(100 - i)),
                "total_prompt_cost": Decimal("10.00"),
                "total_completion_cost": Decimal("10.00"),
                "total_tokens": 100,
                "total_prompt_tokens": 50,
                "total_completion_tokens": 50,
                "record_count": 1,
            }
            for i in range(5)  # DB already applied LIMIT 5
        ]

        cost_repo = AsyncMock()
        daily_repo = AsyncMock()
        default_org_totals = [
            {
                "currency": "USD",
                "total_cost": Decimal("100.00"),
                "total_tokens": 5000,
                "total_prompt_tokens": 2500,
                "total_completion_tokens": 2500,
                "record_count": 10,
            }
        ]
        cost_repo.get_totals_by_org = AsyncMock(return_value=default_org_totals)
        # Return exactly 5 rows (simulating SQL LIMIT)
        cost_repo.get_totals_by_model = AsyncMock(return_value=model_data)
        cost_repo.get_totals_by_project = AsyncMock(return_value=[])
        cost_repo.get_daily_trend = AsyncMock(return_value=[])
        cost_repo.get_totals_by_provider = AsyncMock(return_value=[])

        service = AnalyticsService(cost_repo, daily_repo)
        result = await service.get_top_models(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30), limit=5)
        # Verify limit was passed to repository
        cost_repo.get_totals_by_model.assert_called_once_with(
            _ORG_ID, date(2026, 1, 1), date(2026, 6, 30), limit=5
        )
        assert len(result) == 5
        assert result[0]["model"] == "model-0"  # highest cost

    @pytest.mark.asyncio
    async def test_get_top_projects_limit(self) -> None:
        """RH-05: SQL LIMIT passed through to repository for project breakdown."""
        project_data = [
            {
                "project_id": uuid.uuid4(),
                "currency": "USD",
                "total_cost": Decimal(str(100 - i)),
                "total_tokens": 100,
                "record_count": 1,
            }
            for i in range(3)  # DB already applied LIMIT 3
        ]

        cost_repo = AsyncMock()
        daily_repo = AsyncMock()
        default_org_totals = [
            {
                "currency": "USD",
                "total_cost": Decimal("100.00"),
                "total_tokens": 5000,
                "total_prompt_tokens": 2500,
                "total_completion_tokens": 2500,
                "record_count": 10,
            }
        ]
        cost_repo.get_totals_by_org = AsyncMock(return_value=default_org_totals)
        cost_repo.get_totals_by_model = AsyncMock(return_value=[])
        cost_repo.get_totals_by_project = AsyncMock(return_value=project_data)
        cost_repo.get_daily_trend = AsyncMock(return_value=[])
        cost_repo.get_totals_by_provider = AsyncMock(return_value=[])

        service = AnalyticsService(cost_repo, daily_repo)
        result = await service.get_top_projects(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30), limit=3)
        cost_repo.get_totals_by_project.assert_called_once_with(
            _ORG_ID, date(2026, 1, 1), date(2026, 6, 30), limit=3
        )
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_usage_summary_date_strings(self) -> None:
        service = self._make_service()
        result = await service.get_usage_summary(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert result["start_date"] == "2026-01-01"
        assert result["end_date"] == "2026-06-30"

    @pytest.mark.asyncio
    async def test_get_cost_summary_organization_id(self) -> None:
        service = self._make_service()
        result = await service.get_cost_summary(_ORG_ID, date(2026, 1, 1), date(2026, 6, 30))
        assert result["organization_id"] == str(_ORG_ID)


# ══════════════════════════════════════════════════════════════════════════════
# AggregationService Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAggregationService:
    """Tests for AggregationService — daily summary building."""

    @pytest.mark.asyncio
    async def test_build_daily_summaries_no_records(self) -> None:
        from app.analytics.aggregation import AggregationService

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        service = AggregationService(session)
        summaries = await service.build_daily_summaries(_ORG_ID, _TODAY)
        assert summaries == []

    @pytest.mark.asyncio
    async def test_rebuild_range_returns_count(self) -> None:
        from app.analytics.aggregation import AggregationService

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        service = AggregationService(session)
        count = await service.rebuild_range(
            _ORG_ID,
            date(2026, 6, 1),
            date(2026, 6, 3),
        )
        # 3 days, 0 summaries each
        assert count == 0

    @pytest.mark.asyncio
    async def test_rebuild_range_single_day(self) -> None:
        from app.analytics.aggregation import AggregationService

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        service = AggregationService(session)
        count = await service.rebuild_range(_ORG_ID, _TODAY, _TODAY)
        assert count == 0

    @pytest.mark.asyncio
    async def test_build_daily_summaries_with_rows(self) -> None:
        """Test that rows returned from DB are turned into DailyCostSummary objects."""
        from app.analytics.aggregation import AggregationService

        session = AsyncMock()

        # Mock the aggregation query result
        mock_row = MagicMock()
        mock_row.organization_id = _ORG_ID
        mock_row.project_id = None
        mock_row.provider = "openai"
        mock_row.model = "gpt-4"
        mock_row.currency = "USD"
        mock_row.total_prompt_tokens = 1000
        mock_row.total_completion_tokens = 500
        mock_row.total_cached_tokens = None
        mock_row.total_tokens = 1500
        mock_row.total_requests = 5
        mock_row.total_cost = Decimal("0.05")
        mock_row.total_prompt_cost = Decimal("0.02")
        mock_row.total_completion_cost = Decimal("0.03")
        mock_row.total_cached_cost = None
        mock_row.event_count = 5

        mock_agg_result = MagicMock()
        mock_agg_result.all.return_value = [mock_row]

        # Mock the upsert in the summary repo
        summary = _make_summary()
        mock_upsert_result = MagicMock()
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = summary

        session.execute = AsyncMock(
            side_effect=[mock_agg_result, mock_upsert_result, mock_select_result]
        )
        session.flush = AsyncMock()

        service = AggregationService(session)
        summaries = await service.build_daily_summaries(_ORG_ID, _TODAY)
        assert len(summaries) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Pricing API Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPricingAPI:
    """Tests for pricing API endpoints using the conftest async client."""

    @pytest.mark.asyncio
    async def test_calculate_price_requires_auth(self, client: Any) -> None:
        """POST /pricing/calculate returns 401 without Bearer token."""
        resp = await client.post(
            "/v1/pricing/calculate",
            json={
                "provider": "openai",
                "model": "gpt-4",
                "prompt_tokens": 1000,
                "completion_tokens": 500,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_model_pricing_requires_auth(self, client: Any) -> None:
        """GET /pricing/models returns 401 without Bearer token."""
        resp = await client.get(
            "/v1/pricing/models",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_pricing_providers_requires_auth(self, client: Any) -> None:
        """GET /pricing/providers returns 401 without Bearer token."""
        resp = await client.get(
            "/v1/pricing/providers",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_model_pricing_requires_auth(self, client: Any) -> None:
        """POST /pricing/models returns 401 without Bearer token."""
        resp = await client.post(
            "/v1/pricing/models",
            json={
                "provider": "openai",
                "model": "gpt-4",
                "version": "v1",
                "effective_from": "2024-01-01",
                "prompt_token_price": "0.00001",
                "completion_token_price": "0.00003",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_models_with_mock_auth(self, app: Any) -> None:
        """GET /pricing/models returns 200 with mocked auth + DB."""
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/pricing/models",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_providers_with_mock_auth(self, app: Any) -> None:
        """GET /pricing/providers returns 200 with mocked auth + DB."""
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["anthropic", "openai"]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/pricing/providers",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_calculate_price_not_found_with_mock(self, app: Any) -> None:
        """POST /pricing/calculate returns 404 when no pricing found."""
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no pricing found
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/v1/pricing/calculate",
                    json={
                        "provider": "openai",
                        "model": "gpt-4-nonexistent",
                        "prompt_tokens": 1000,
                        "completion_tokens": 500,
                    },
                )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_calculate_price_success_with_mock(self, app: Any) -> None:
        """POST /pricing/calculate returns 200 with valid pricing."""
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        pricing = _make_pricing(
            prompt_price=Decimal("0.00001"),
            completion_price=Decimal("0.00003"),
        )
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pricing
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/v1/pricing/calculate",
                    json={
                        "provider": "openai",
                        "model": "gpt-4",
                        "prompt_tokens": 1000,
                        "completion_tokens": 500,
                        "usage_date": "2026-01-15",
                    },
                )
            assert response.status_code == 200
            data = response.json()
            assert "total_cost" in data
            assert "prompt_cost" in data
            assert data["provider"] == "openai"
        finally:
            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Analytics API Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAnalyticsAPI:
    """Tests for analytics API endpoints using conftest async client."""

    @pytest.mark.asyncio
    async def test_usage_summary_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/analytics/usage",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_cost_summary_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/analytics/cost",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_provider_breakdown_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/analytics/providers",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_model_breakdown_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/analytics/models",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_project_breakdown_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/analytics/projects",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_org_summary_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            f"/v1/analytics/organizations/{_ORG_ID}/summary",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    def _make_mock_session_with_totals(self) -> Any:
        """Create a mock DB session returning zero aggregates."""
        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.total_cost = Decimal("0")
        mock_row.total_tokens = 0
        mock_row.total_prompt_tokens = 0
        mock_row.total_completion_tokens = 0
        mock_row.record_count = 0
        mock_one = MagicMock()
        mock_one.one.return_value = mock_row
        mock_all = MagicMock()
        mock_all.all.return_value = []
        # Return one-type for get_totals, all-type for breakdowns
        mock_session.execute = AsyncMock(side_effect=[mock_one, mock_all])
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        return mock_session

    @pytest.mark.asyncio
    async def test_usage_summary_with_mock_auth(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.total_cost = Decimal("0")
        mock_row.total_tokens = 0
        mock_row.total_prompt_tokens = 0
        mock_row.total_completion_tokens = 0
        mock_row.record_count = 0
        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/analytics/usage",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert response.status_code == 200
            data = response.json()
            assert "total_tokens" in data
            assert "total_requests" in data
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cost_summary_with_mock_auth(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.currency = "USD"
        mock_row.total_cost = Decimal("100.00")
        mock_row.total_tokens = 5000
        mock_row.total_prompt_tokens = 2500
        mock_row.total_completion_tokens = 2500
        mock_row.record_count = 10
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/analytics/cost",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert response.status_code == 200
            data = response.json()
            assert "total_cost" in data
            assert data["record_count"] == 10
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_provider_breakdown_with_mock_auth(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/analytics/providers",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_model_breakdown_with_mock_auth(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/analytics/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_project_breakdown_with_mock_auth(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/v1/analytics/projects",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_org_summary_with_mock_auth(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User
        from app.api.deps import get_db

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.total_cost = Decimal("0")
        mock_row.total_tokens = 0
        mock_row.total_prompt_tokens = 0
        mock_row.total_completion_tokens = 0
        mock_row.record_count = 0
        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    f"/v1/analytics/organizations/{_ORG_ID}/summary",
                    params={
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert response.status_code == 200
            data = response.json()
            assert "total_cost" in data
            assert "total_tokens" in data
        finally:
            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Schema Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPricingSchemas:
    """Tests for pricing schemas."""

    def test_model_pricing_response_from_orm(self) -> None:
        from app.schemas.pricing import ModelPricingResponse
        pricing = _make_pricing()
        response = ModelPricingResponse.from_orm_model(pricing)
        assert response.provider == "openai"
        assert response.model == "gpt-4"
        assert isinstance(response.prompt_token_price, str)
        assert isinstance(response.completion_token_price, str)

    def test_model_pricing_response_decimal_as_string(self) -> None:
        from app.schemas.pricing import ModelPricingResponse
        pricing = _make_pricing(prompt_price=Decimal("0.00001"))
        response = ModelPricingResponse.from_orm_model(pricing)
        # Should be string representation
        assert "0.00001" in response.prompt_token_price

    def test_price_calculation_response(self) -> None:
        from app.schemas.pricing import PriceCalculationResponse
        response = PriceCalculationResponse(
            provider="openai",
            model="gpt-4",
            currency="USD",
            prompt_tokens=1000,
            completion_tokens=500,
            cached_tokens=None,
            total_tokens=1500,
            prompt_cost="0.01000000",
            completion_cost="0.01500000",
            cached_cost=None,
            total_cost="0.02500000",
            model_pricing_id=_PRICING_ID,
            calculation_version="1.0",
            pricing_date=_TODAY,
        )
        assert response.total_cost == "0.02500000"

    def test_model_pricing_create_validation(self) -> None:
        from app.schemas.pricing import ModelPricingCreate
        create = ModelPricingCreate(
            provider="openai",
            model="gpt-4",
            version="v1",
            effective_from=date(2024, 1, 1),
            prompt_token_price=Decimal("0.00001"),
            completion_token_price=Decimal("0.00003"),
        )
        assert create.currency == "USD"
        assert create.is_active is True

    def test_model_pricing_create_invalid_date_range(self) -> None:
        from app.schemas.pricing import ModelPricingCreate
        with pytest.raises(Exception):
            ModelPricingCreate(
                provider="openai",
                model="gpt-4",
                version="v1",
                effective_from=date(2024, 6, 1),
                effective_to=date(2024, 1, 1),  # before effective_from
                prompt_token_price=Decimal("0.00001"),
                completion_token_price=Decimal("0.00003"),
            )

    def test_model_pricing_list_response(self) -> None:
        from app.schemas.pricing import ModelPricingListResponse, ModelPricingResponse
        pricing = _make_pricing()
        item = ModelPricingResponse.from_orm_model(pricing)
        response = ModelPricingListResponse(
            items=[item],
            total=1,
            has_more=False,
        )
        assert response.total == 1
        assert len(response.items) == 1


class TestAnalyticsSchemas:
    """Tests for analytics schemas."""

    def test_cost_summary_response(self) -> None:
        from app.schemas.analytics import CostSummaryResponse
        resp = CostSummaryResponse(
            organization_id=str(_ORG_ID),
            start_date="2026-01-01",
            end_date="2026-06-30",
            total_cost="100.00",
            total_tokens=5000,
            record_count=10,
        )
        assert resp.total_cost == "100.00"

    def test_usage_summary_response(self) -> None:
        from app.schemas.analytics import UsageSummaryResponse
        resp = UsageSummaryResponse(
            organization_id=str(_ORG_ID),
            start_date="2026-01-01",
            end_date="2026-06-30",
            total_tokens=5000,
            total_prompt_tokens=2500,
            total_completion_tokens=2500,
            total_requests=10,
            event_count=10,
        )
        assert resp.total_tokens == 5000

    def test_provider_breakdown_item(self) -> None:
        from app.schemas.analytics import ProviderBreakdownItem
        item = ProviderBreakdownItem(
            provider="openai",
            currency="USD",
            total_cost="80.00",
            total_prompt_cost="30.00",
            total_completion_cost="50.00",
            total_tokens=4000,
            total_prompt_tokens=2000,
            total_completion_tokens=2000,
            record_count=8,
        )
        assert item.provider == "openai"

    def test_model_breakdown_item(self) -> None:
        from app.schemas.analytics import ModelBreakdownItem
        item = ModelBreakdownItem(
            provider="openai",
            model="gpt-4",
            currency="USD",
            total_cost="80.00",
            total_prompt_cost="30.00",
            total_completion_cost="50.00",
            total_tokens=4000,
            total_prompt_tokens=2000,
            total_completion_tokens=2000,
            record_count=8,
        )
        assert item.model == "gpt-4"

    def test_project_breakdown_item(self) -> None:
        from app.schemas.analytics import ProjectBreakdownItem
        item = ProjectBreakdownItem(
            project_id=str(_PROJECT_ID),
            currency="USD",
            total_cost="50.00",
            total_tokens=2500,
            record_count=5,
        )
        assert item.project_id == str(_PROJECT_ID)

    def test_project_breakdown_item_no_project(self) -> None:
        from app.schemas.analytics import ProjectBreakdownItem
        item = ProjectBreakdownItem(
            project_id=None,
            currency="USD",
            total_cost="50.00",
            total_tokens=2500,
            record_count=5,
        )
        assert item.project_id is None

    def test_daily_trend_item(self) -> None:
        from app.schemas.analytics import DailyTrendItem
        item = DailyTrendItem(
            usage_date="2026-06-01",
            currency="USD",
            total_cost="10.00",
            total_prompt_cost="4.00",
            total_completion_cost="6.00",
            total_tokens=500,
            record_count=2,
        )
        assert item.usage_date == "2026-06-01"

    def test_org_summary_response(self) -> None:
        from app.schemas.analytics import OrgSummaryResponse
        resp = OrgSummaryResponse(
            organization_id=str(_ORG_ID),
            start_date="2026-01-01",
            end_date="2026-06-30",
            total_tokens=5000,
            total_prompt_tokens=2500,
            total_completion_tokens=2500,
            total_requests=10,
            event_count=10,
            total_cost="100.00",
        )
        assert resp.total_cost == "100.00"
