"""Tests for the Usage Ingestion Platform (EP-16).

Covers:
  - IngestUsageRequest schema validation (provider/model/tokens/cost/
    currency/timestamp/metadata size)
  - UsageRecordRepository (lookup, aggregates)
  - UsageIngestionService (dedup, ownership, dual-write, race handling)
  - POST /v1/ingest/usage end-to-end (auth, permissions, ownership,
    duplicates, validation errors, concurrency)
  - Performance smoke (query budget, latency)

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.models.organization import OrganizationStatus
from app.schemas.usage_ingestion import MAX_METADATA_BYTES, IngestUsageRequest
from app.services.usage_ingestion_service import (
    UnknownProjectError,
    UsageIngestionService,
    _split_cost,
)
from tests.conftest import make_api_key, make_org, make_project, make_usage_record

_ORG_ID = uuid.uuid4()
_RAW_KEY = "costorah_live_" + "z" * 43


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "provider": "openai",
        "model": "gpt-4.1",
        "request_id": "req_123456",
        "input_tokens": 1200,
        "output_tokens": 320,
        "cached_tokens": 0,
        "total_tokens": 1520,
        "cost": 0.0812,
        "currency": "USD",
        "latency_ms": 742,
        "status": "success",
        "region": "us-east-1",
        "metadata": {"user": "john", "environment": "production"},
    }
    payload.update(overrides)
    return payload


# ══════════════════════════════════════════════════════════════════════════════
# Schema validation
# ══════════════════════════════════════════════════════════════════════════════


class TestIngestUsageRequestValidation:
    def test_accepts_full_valid_payload(self) -> None:
        req = IngestUsageRequest(**_valid_payload())
        assert req.provider == "openai"
        assert req.resolved_total_tokens == 1520

    def test_accepts_minimal_payload(self) -> None:
        req = IngestUsageRequest(provider="openai", model="gpt-4.1", request_id="r1", cost=0.01)
        assert req.resolved_total_tokens == 0
        assert req.currency == "USD"
        assert req.status == "success"

    @pytest.mark.parametrize(
        "provider",
        [
            "openai",
            "anthropic",
            "google",
            "azure_openai",
            "grok",
            "openrouter",
            "ollama",
            "cohere",
            "bedrock",
            "mistral",
        ],
    )
    def test_accepts_every_catalog_provider(self, provider: str) -> None:
        req = IngestUsageRequest(**_valid_payload(provider=provider))
        assert req.provider == provider

    def test_provider_is_case_insensitive(self) -> None:
        req = IngestUsageRequest(**_valid_payload(provider="OpenAI"))
        assert req.provider == "openai"

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported provider"):
            IngestUsageRequest(**_valid_payload(provider="not-a-real-provider"))

    def test_rejects_blank_model(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(**_valid_payload(model="   "))

    def test_rejects_negative_input_tokens(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(**_valid_payload(input_tokens=-1))

    def test_rejects_negative_output_tokens(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(**_valid_payload(output_tokens=-1))

    def test_rejects_mismatched_total_tokens(self) -> None:
        with pytest.raises(ValidationError, match="total_tokens"):
            IngestUsageRequest(**_valid_payload(total_tokens=9999))

    def test_total_tokens_optional_and_derived(self) -> None:
        payload = _valid_payload()
        del payload["total_tokens"]
        req = IngestUsageRequest(**payload)
        assert req.resolved_total_tokens == 1520

    def test_rejects_cached_tokens_exceeding_input_tokens(self) -> None:
        with pytest.raises(ValidationError, match="cached_tokens"):
            IngestUsageRequest(**_valid_payload(cached_tokens=99999))

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(**_valid_payload(cost=-0.01))

    def test_accepts_zero_cost(self) -> None:
        req = IngestUsageRequest(**_valid_payload(cost=0))
        assert req.cost == Decimal(0)

    def test_rejects_non_alphabetic_currency(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(**_valid_payload(currency="US1"))

    def test_currency_normalized_to_uppercase(self) -> None:
        req = IngestUsageRequest(**_valid_payload(currency="usd"))
        assert req.currency == "USD"

    def test_rejects_far_future_timestamp(self) -> None:
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        with pytest.raises(ValidationError, match="future"):
            IngestUsageRequest(**_valid_payload(timestamp=future))

    def test_accepts_near_future_timestamp_clock_drift(self) -> None:
        near_future = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
        req = IngestUsageRequest(**_valid_payload(timestamp=near_future))
        assert req.timestamp is not None

    def test_missing_timestamp_resolves_to_now(self) -> None:
        payload = _valid_payload()
        payload.pop("timestamp", None)
        req = IngestUsageRequest(**payload)
        assert (datetime.now(UTC) - req.resolved_timestamp) < timedelta(seconds=5)

    def test_rejects_oversized_metadata(self) -> None:
        huge_metadata = {"blob": "x" * (MAX_METADATA_BYTES + 1)}
        with pytest.raises(ValidationError, match="too large"):
            IngestUsageRequest(**_valid_payload(metadata=huge_metadata))

    def test_accepts_metadata_under_limit(self) -> None:
        req = IngestUsageRequest(**_valid_payload(metadata={"k": "v"}))
        assert req.metadata == {"k": "v"}

    def test_rejects_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(**_valid_payload(status="not-a-status"))

    @pytest.mark.parametrize("status", ["success", "error", "timeout", "cancelled"])
    def test_accepts_every_status(self, status: str) -> None:
        req = IngestUsageRequest(**_valid_payload(status=status))
        assert req.status == status

    def test_rejects_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            IngestUsageRequest(model="gpt-4.1", request_id="r1", cost=0.01)  # type: ignore[call-arg]


class TestSplitCost:
    def test_splits_proportionally_to_tokens(self) -> None:
        prompt, completion = _split_cost(Decimal("1.00"), 800, 200)
        assert prompt == Decimal("0.80000000")
        assert completion == Decimal("0.20000000")
        assert prompt + completion == Decimal("1.00000000")

    def test_zero_tokens_attributes_all_to_completion(self) -> None:
        prompt, completion = _split_cost(Decimal("1.00"), 0, 0)
        assert prompt == Decimal("0")
        assert completion == Decimal("1.00")

    def test_sum_always_equals_total_cost(self) -> None:
        prompt, completion = _split_cost(Decimal("0.0812"), 1200, 320)
        assert prompt + completion == Decimal("0.0812")


# ══════════════════════════════════════════════════════════════════════════════
# Repository
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageRecordRepositoryGetByRequestId:
    @pytest.mark.asyncio
    async def test_returns_matching_record(self) -> None:
        from app.repositories.usage_record_repository import UsageRecordRepository

        record = make_usage_record(org_id=_ORG_ID, request_id="req_1")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = UsageRecordRepository(mock_session)
        result = await repo.get_by_request_id(_ORG_ID, "req_1")
        assert result is record

    @pytest.mark.asyncio
    async def test_returns_none_when_absent(self) -> None:
        from app.repositories.usage_record_repository import UsageRecordRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = UsageRecordRepository(mock_session)
        result = await repo.get_by_request_id(_ORG_ID, "unknown")
        assert result is None


class TestUsageRecordRepositoryAggregates:
    @pytest.mark.asyncio
    async def test_daily_totals_shape(self) -> None:
        from app.repositories.usage_record_repository import UsageRecordRepository

        row = MagicMock(
            usage_date=datetime.now(UTC).date(),
            currency="USD",
            total_cost=Decimal("12.50"),
            total_tokens=5000,
            record_count=3,
        )
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = UsageRecordRepository(mock_session)
        today = datetime.now(UTC).date()
        result = await repo.get_daily_totals(_ORG_ID, today, today)
        assert result == [
            {
                "usage_date": row.usage_date,
                "currency": "USD",
                "total_cost": Decimal("12.50"),
                "total_tokens": 5000,
                "record_count": 3,
            }
        ]

    @pytest.mark.asyncio
    async def test_monthly_totals_empty(self) -> None:
        from app.repositories.usage_record_repository import UsageRecordRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = UsageRecordRepository(mock_session)
        today = datetime.now(UTC).date()
        result = await repo.get_monthly_totals(_ORG_ID, today, today)
        assert result == []

    @pytest.mark.asyncio
    async def test_totals_by_provider_shape(self) -> None:
        from app.repositories.usage_record_repository import UsageRecordRepository

        row = MagicMock(
            provider="openai",
            currency="USD",
            total_cost=Decimal("5.00"),
            total_tokens=1000,
            record_count=1,
        )
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = UsageRecordRepository(mock_session)
        today = datetime.now(UTC).date()
        result = await repo.get_totals_by_provider(_ORG_ID, today, today)
        assert result[0]["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_totals_by_model_applies_limit(self) -> None:
        from app.repositories.usage_record_repository import UsageRecordRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = UsageRecordRepository(mock_session)
        today = datetime.now(UTC).date()
        await repo.get_totals_by_model(_ORG_ID, today, today, limit=5)
        stmt = mock_session.execute.await_args.args[0]
        assert stmt._limit_clause is not None


# ══════════════════════════════════════════════════════════════════════════════
# UsageIngestionService
# ══════════════════════════════════════════════════════════════════════════════


def _mock_ingestion_session() -> AsyncMock:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


class TestUsageIngestionServiceDuplicate:
    @pytest.mark.asyncio
    async def test_duplicate_request_id_returns_existing_without_writing(self) -> None:
        org = make_org()
        org.id = _ORG_ID
        existing = make_usage_record(org_id=_ORG_ID, request_id="req_1")
        payload = IngestUsageRequest(**_valid_payload(request_id="req_1"))

        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        with patch.object(
            service._usage_repo,
            "get_by_request_id",
            new=AsyncMock(return_value=existing),
        ) as get_dup:
            record, is_duplicate = await service.ingest(
                organization=org, api_key_id=None, payload=payload
            )
        assert record is existing
        assert is_duplicate is True
        get_dup.assert_awaited_once_with(_ORG_ID, "req_1")
        session.flush.assert_not_awaited()


class TestUsageIngestionServiceProjectOwnership:
    @pytest.mark.asyncio
    async def test_unknown_project_raises(self) -> None:
        org = make_org()
        org.id = _ORG_ID
        payload = IngestUsageRequest(**_valid_payload(project_id=str(uuid.uuid4())))
        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(service._project_repo, "get", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(UnknownProjectError):
                await service.ingest(organization=org, api_key_id=None, payload=payload)

    @pytest.mark.asyncio
    async def test_project_from_another_org_raises(self) -> None:
        org = make_org()
        org.id = _ORG_ID
        other_org_project = make_project(org_id=uuid.uuid4())
        payload = IngestUsageRequest(**_valid_payload(project_id=str(other_org_project.id)))
        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(
                service._project_repo, "get", new=AsyncMock(return_value=other_org_project)
            ),
        ):
            with pytest.raises(UnknownProjectError):
                await service.ingest(organization=org, api_key_id=None, payload=payload)

    @pytest.mark.asyncio
    async def test_project_from_same_org_succeeds(self) -> None:
        org = make_org()
        org.id = _ORG_ID
        project = make_project(org_id=_ORG_ID)
        payload = IngestUsageRequest(**_valid_payload(project_id=str(project.id)))

        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(service._project_repo, "get", new=AsyncMock(return_value=project)),
            patch.object(service._usage_repo, "create", new=AsyncMock(side_effect=lambda r: r)),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(side_effect=lambda e: e),
            ),
            patch(
                "app.repositories.usage_cost_record_repository.UsageCostRecordRepository.upsert",
                new=AsyncMock(side_effect=lambda c: c),
            ),
            patch(
                "app.analytics.aggregation.AggregationService.build_daily_summaries",
                new=AsyncMock(return_value=[]),
            ),
        ):
            record, is_duplicate = await service.ingest(
                organization=org, api_key_id=None, payload=payload
            )
        assert record.project_id == project.id
        assert is_duplicate is False


class TestUsageIngestionServiceCreate:
    @pytest.mark.asyncio
    async def test_creates_record_and_feeds_dashboard_tables(self) -> None:
        org = make_org()
        org.id = _ORG_ID
        api_key_id = uuid.uuid4()
        payload = IngestUsageRequest(**_valid_payload())

        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(service._usage_repo, "create", new=AsyncMock(side_effect=lambda r: r)),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(side_effect=lambda e: e),
            ) as event_upsert,
            patch(
                "app.repositories.usage_cost_record_repository.UsageCostRecordRepository.upsert",
                new=AsyncMock(side_effect=lambda c: c),
            ) as cost_upsert,
            patch(
                "app.analytics.aggregation.AggregationService.build_daily_summaries",
                new=AsyncMock(return_value=[]),
            ) as build_summaries,
        ):
            record, is_duplicate = await service.ingest(
                organization=org, api_key_id=api_key_id, payload=payload
            )

        assert is_duplicate is False
        assert record.organization_id == _ORG_ID
        assert record.api_key_id == api_key_id
        assert record.provider == "openai"
        assert record.cost == Decimal("0.0812")
        event_upsert.assert_awaited_once()
        cost_upsert.assert_awaited_once()
        build_summaries.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dashboard_feed_uses_caller_reported_total_cost(self) -> None:
        org = make_org()
        org.id = _ORG_ID
        payload = IngestUsageRequest(**_valid_payload(cost=1.50))

        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        captured: dict[str, Any] = {}

        async def _capture_cost_upsert(cost_record: Any) -> Any:
            captured["total_cost"] = cost_record.total_cost
            captured["prompt_cost"] = cost_record.prompt_cost
            captured["completion_cost"] = cost_record.completion_cost
            return cost_record

        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(service._usage_repo, "create", new=AsyncMock(side_effect=lambda r: r)),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(side_effect=lambda e: e),
            ),
            patch(
                "app.repositories.usage_cost_record_repository.UsageCostRecordRepository.upsert",
                new=AsyncMock(side_effect=_capture_cost_upsert),
            ),
            patch(
                "app.analytics.aggregation.AggregationService.build_daily_summaries",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await service.ingest(organization=org, api_key_id=None, payload=payload)

        assert captured["total_cost"] == Decimal("1.50")
        assert captured["prompt_cost"] + captured["completion_cost"] == Decimal("1.50")

    @pytest.mark.asyncio
    async def test_race_condition_resolves_to_duplicate(self) -> None:
        """Two requests with the same request_id arrive concurrently; the
        loser's INSERT hits the DB unique constraint. It must not error —
        it must resolve to the winner's record, same as a normal duplicate.
        """
        from sqlalchemy.exc import IntegrityError

        org = make_org()
        org.id = _ORG_ID
        winner_record = make_usage_record(org_id=_ORG_ID, request_id="req_race")
        payload = IngestUsageRequest(**_valid_payload(request_id="req_race"))

        session = _mock_ingestion_session()
        service = UsageIngestionService(session)

        call_count = {"n": 0}

        async def _get_by_request_id_side_effect(*_args: Any, **_kwargs: Any) -> Any:
            call_count["n"] += 1
            # First call (pre-insert check): not found yet.
            # Second call (post-IntegrityError recovery): the winner's row.
            return None if call_count["n"] == 1 else winner_record

        with (
            patch.object(
                service._usage_repo,
                "get_by_request_id",
                new=AsyncMock(side_effect=_get_by_request_id_side_effect),
            ),
            patch.object(
                service._usage_repo,
                "create",
                new=AsyncMock(side_effect=IntegrityError("insert", {}, Exception("dup"))),
            ),
        ):
            record, is_duplicate = await service.ingest(
                organization=org, api_key_id=None, payload=payload
            )

        assert record is winner_record
        assert is_duplicate is True
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_race_condition_reraises_if_truly_unresolved(self) -> None:
        """If the IntegrityError wasn't actually the dedup race (re-query still
        finds nothing), the original error must propagate, not be swallowed."""
        from sqlalchemy.exc import IntegrityError

        org = make_org()
        org.id = _ORG_ID
        payload = IngestUsageRequest(**_valid_payload(request_id="req_mystery"))

        session = _mock_ingestion_session()
        service = UsageIngestionService(session)
        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(
                service._usage_repo,
                "create",
                new=AsyncMock(side_effect=IntegrityError("insert", {}, Exception("dup"))),
            ),
        ):
            with pytest.raises(IntegrityError):
                await service.ingest(organization=org, api_key_id=None, payload=payload)


# ══════════════════════════════════════════════════════════════════════════════
# API integration: POST /v1/ingest/usage
# ══════════════════════════════════════════════════════════════════════════════


def _active_org(org_id: uuid.UUID = _ORG_ID) -> Any:
    from app.models.organization import Organization

    org = MagicMock(spec=Organization)
    org.id = org_id
    org.status = OrganizationStatus.ACTIVE
    org.slug = "acme"
    return org


def _patch_key_lookup(key: Any, org: Any) -> Any:
    return patch.multiple(
        "app.services.api_key_auth_service",
        OrganizationApiKeyRepository=MagicMock(
            return_value=MagicMock(
                get_by_hash=AsyncMock(return_value=key),
                update_last_used=AsyncMock(side_effect=lambda k: k),
            )
        ),
        OrganizationRepository=MagicMock(return_value=MagicMock(get=AsyncMock(return_value=org))),
    )


def _no_op_db_override(app: Any) -> None:
    from app.api.deps import get_db

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_db] = mock_get_db


@contextmanager
def _patch_ingestion_writes() -> Any:
    with (
        patch(
            "app.repositories.usage_record_repository.UsageRecordRepository.get_by_request_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.repositories.usage_record_repository.UsageRecordRepository.create",
            new=AsyncMock(side_effect=lambda r: r),
        ),
        patch(
            "app.repositories.usage_event_repository.UsageEventRepository.upsert",
            new=AsyncMock(side_effect=lambda e: e),
        ),
        patch(
            "app.repositories.usage_cost_record_repository.UsageCostRecordRepository.upsert",
            new=AsyncMock(side_effect=lambda c: c),
        ),
        patch(
            "app.analytics.aggregation.AggregationService.build_daily_summaries",
            new=AsyncMock(return_value=[]),
        ),
    ):
        yield


class TestIngestUsageEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/ingest/usage", json=_valid_payload())
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_successful_ingestion_returns_200(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        try:
            with _patch_key_lookup(key, org), _patch_ingestion_writes():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["duplicate"] is False
            assert body["request_id"] == "req_123456"
            assert "usage_id" in body
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_missing_permission_is_403(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=[])
        org = _active_org()
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Insufficient API Key permissions"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_suspended_organization_is_403(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        org.status = OrganizationStatus.SUSPENDED
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Organization suspended"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_expired_key_is_401(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        key.expires_at = datetime.now(UTC) - timedelta(days=1)
        try:
            with _patch_key_lookup(key, None):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 401
            assert resp.json()["detail"] == "API Key expired"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_payload_is_422(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(provider="not-a-provider"),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_oversized_metadata_is_422(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(metadata={"blob": "x" * (MAX_METADATA_BYTES + 1)}),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_project_is_404(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        try:
            with (
                _patch_key_lookup(key, org),
                patch(
                    "app.repositories.usage_record_repository."
                    "UsageRecordRepository.get_by_request_id",
                    new=AsyncMock(return_value=None),
                ),
                patch(
                    "app.repositories.project_repository.ProjectRepository.get",
                    new=AsyncMock(return_value=None),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(project_id=str(uuid.uuid4())),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_duplicate_request_id_returns_200_with_duplicate_true(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        existing = make_usage_record(org_id=_ORG_ID, request_id="req_dup")
        try:
            with (
                _patch_key_lookup(key, org),
                patch(
                    "app.repositories.usage_record_repository."
                    "UsageRecordRepository.get_by_request_id",
                    new=AsyncMock(return_value=existing),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(request_id="req_dup"),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["duplicate"] is True
            assert body["usage_id"] == str(existing.id)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_response_never_contains_api_key_or_hash(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()
        try:
            with _patch_key_lookup(key, org), _patch_ingestion_writes():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/ingest/usage",
                        json=_valid_payload(),
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert _RAW_KEY not in resp.text
            assert key.key_hash not in resp.text
        finally:
            app.dependency_overrides.clear()


class TestIngestUsageConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_requests_with_distinct_ids_all_succeed(self, app: Any) -> None:
        _no_op_db_override(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["usage:write"])
        org = _active_org()

        async def _post(request_id: str) -> int:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/ingest/usage",
                    json=_valid_payload(request_id=request_id),
                    headers={"Authorization": f"Bearer {_RAW_KEY}"},
                )
            return resp.status_code

        try:
            with _patch_key_lookup(key, org), _patch_ingestion_writes():
                statuses = await asyncio.gather(*(_post(f"req_concurrent_{i}") for i in range(10)))
            assert statuses == [200] * 10
        finally:
            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Performance smoke
# ══════════════════════════════════════════════════════════════════════════════


class TestPerformance:
    @pytest.mark.asyncio
    async def test_new_record_ingest_is_fast_with_mocked_io(self) -> None:
        import time

        org = make_org()
        org.id = _ORG_ID
        payload = IngestUsageRequest(**_valid_payload())
        session = _mock_ingestion_session()
        service = UsageIngestionService(session)

        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=None)
            ),
            patch.object(service._usage_repo, "create", new=AsyncMock(side_effect=lambda r: r)),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(side_effect=lambda e: e),
            ),
            patch(
                "app.repositories.usage_cost_record_repository.UsageCostRecordRepository.upsert",
                new=AsyncMock(side_effect=lambda c: c),
            ),
            patch(
                "app.analytics.aggregation.AggregationService.build_daily_summaries",
                new=AsyncMock(return_value=[]),
            ),
        ):
            start = time.monotonic()
            await service.ingest(organization=org, api_key_id=None, payload=payload)
            elapsed = time.monotonic() - start

        assert elapsed < 0.25

    @pytest.mark.asyncio
    async def test_duplicate_lookup_does_not_touch_project_repo(self) -> None:
        """The fast dedup path must short-circuit before any ownership
        lookup — no wasted queries on a request we're about to discard."""
        org = make_org()
        org.id = _ORG_ID
        existing = make_usage_record(org_id=_ORG_ID, request_id="req_1")
        payload = IngestUsageRequest(**_valid_payload(request_id="req_1"))
        session = _mock_ingestion_session()
        service = UsageIngestionService(session)

        with (
            patch.object(
                service._usage_repo, "get_by_request_id", new=AsyncMock(return_value=existing)
            ),
            patch.object(service._project_repo, "get", new=AsyncMock()) as project_get,
        ):
            await service.ingest(organization=org, api_key_id=None, payload=payload)

        project_get.assert_not_awaited()
