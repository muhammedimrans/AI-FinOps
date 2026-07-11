"""Tests for PlaygroundService — EP-25.4 (AI Playground).

Exercises the orchestration logic (decrypt -> build config -> adapter ->
usage write -> cost attribution) hermetically: the adapter's ``complete()``
is patched directly (its own HTTP shape is covered by
test_ep25_4_playground_adapters.py), and every repository write is patched
at the class-method boundary rather than requiring a real database
connection — consistent with every other service-layer test in this suite
that doesn't have DATABASE_URL available.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.playground_execution import PlaygroundExecutionStatus
from app.models.provider_connection import ProviderConnection, ProviderType
from app.models.usage_event import UsageEvent
from app.providers.models import ProviderResponse, UsageData
from app.services.playground_service import PlaygroundService


def _connection(provider_type: ProviderType = ProviderType.OPENAI) -> ProviderConnection:
    conn = ProviderConnection()
    conn.id = uuid.uuid4()
    conn.provider_type = provider_type
    conn.encrypted_api_key = "v1:fake-ciphertext"
    conn.base_url = None
    return conn


def _service() -> PlaygroundService:
    session = AsyncMock()
    credentials = AsyncMock()
    credentials.decrypt = lambda _ciphertext: "sk-decrypted"
    return PlaygroundService(session, credentials=credentials)


class TestExecuteSuccess:
    @pytest.mark.asyncio
    async def test_success_writes_usage_event_and_cost_record(self) -> None:
        service = _service()
        connection = _connection()
        response = ProviderResponse(
            model_id="gpt-4o",
            content="Hello from GPT",
            usage=UsageData(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            finish_reason="stop",
        )
        fake_adapter = AsyncMock()
        fake_adapter.complete = AsyncMock(return_value=response)
        fake_adapter.aclose = AsyncMock()

        fake_usage_event = UsageEvent()
        fake_usage_event.id = uuid.uuid4()
        fake_usage_event.organization_id = uuid.uuid4()
        fake_usage_event.provider = "openai"
        fake_usage_event.model = "gpt-4o"
        fake_usage_event.prompt_tokens = 10
        fake_usage_event.completion_tokens = 5
        fake_usage_event.cached_tokens = None
        fake_usage_event.total_tokens = 15
        fake_usage_event.timestamp = datetime.now(UTC)

        with (
            patch("app.services.playground_service.build_provider_config", return_value=object()),
            patch("app.providers.factory.ProviderFactory.create", return_value=fake_adapter),
            patch(
                "app.repositories.playground_execution_repository.PlaygroundExecutionRepository.create",
                new=AsyncMock(side_effect=lambda x: x),
            ),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(return_value=fake_usage_event),
            ) as mock_upsert_event,
            patch(
                "app.pricing.engine.PricingEngine.calculate_event_cost",
                new=AsyncMock(
                    return_value={
                        "prompt_cost": Decimal("0.0001"),
                        "completion_cost": Decimal("0.0002"),
                        "cached_cost": None,
                        "total_cost": Decimal("0.0003"),
                        "currency": "USD",
                        "model_pricing_id": uuid.uuid4(),
                        "calculation_version": "v1",
                    }
                ),
            ),
            patch(
                "app.repositories.usage_cost_record_repository.UsageCostRecordRepository.upsert",
                new=AsyncMock(),
            ) as mock_upsert_cost,
        ):
            execution = await service.execute(
                organization_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                connection=connection,
                project_id=None,
                model_id="gpt-4o",
                system_prompt="Be nice",
                user_prompt="Hi",
                temperature=0.5,
                top_p=None,
                max_tokens=100,
            )

        assert execution.status == PlaygroundExecutionStatus.SUCCEEDED
        assert execution.response_text == "Hello from GPT"
        assert execution.prompt_tokens == 10
        assert execution.completion_tokens == 5
        assert execution.total_tokens == 15
        assert execution.estimated_cost == Decimal("0.0003")
        assert execution.currency == "USD"
        assert execution.usage_event_id == fake_usage_event.id
        assert mock_upsert_event.await_count == 1
        assert mock_upsert_cost.await_count == 1
        fake_adapter.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_pricing_leaves_cost_none_but_still_succeeds(self) -> None:
        service = _service()
        connection = _connection()
        response = ProviderResponse(
            model_id="unpriced-model",
            content="ok",
            usage=UsageData(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        fake_adapter = AsyncMock()
        fake_adapter.complete = AsyncMock(return_value=response)
        fake_adapter.aclose = AsyncMock()

        fake_usage_event = UsageEvent()
        fake_usage_event.id = uuid.uuid4()
        fake_usage_event.provider = "openai"
        fake_usage_event.model = "unpriced-model"
        fake_usage_event.prompt_tokens = 1
        fake_usage_event.completion_tokens = 1
        fake_usage_event.total_tokens = 2
        fake_usage_event.timestamp = datetime.now(UTC)

        from app.pricing.engine import PricingNotFoundError

        with (
            patch("app.services.playground_service.build_provider_config", return_value=object()),
            patch("app.providers.factory.ProviderFactory.create", return_value=fake_adapter),
            patch(
                "app.repositories.playground_execution_repository.PlaygroundExecutionRepository.create",
                new=AsyncMock(side_effect=lambda x: x),
            ),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(return_value=fake_usage_event),
            ),
            patch(
                "app.pricing.engine.PricingEngine.calculate_event_cost",
                new=AsyncMock(side_effect=PricingNotFoundError("no pricing")),
            ),
        ):
            execution = await service.execute(
                organization_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                connection=connection,
                project_id=None,
                model_id="unpriced-model",
                system_prompt=None,
                user_prompt="Hi",
                temperature=None,
                top_p=None,
                max_tokens=None,
            )

        assert execution.status == PlaygroundExecutionStatus.SUCCEEDED
        assert execution.estimated_cost is None
        assert execution.usage_event_id == fake_usage_event.id


class TestExecuteFailure:
    @pytest.mark.asyncio
    async def test_provider_error_persists_failed_execution_no_usage_written(self) -> None:
        service = _service()
        connection = _connection()

        with (
            patch("app.services.playground_service.build_provider_config", return_value=object()),
            patch(
                "app.providers.factory.ProviderFactory.create",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "app.repositories.playground_execution_repository.PlaygroundExecutionRepository.create",
                new=AsyncMock(side_effect=lambda x: x),
            ) as mock_create,
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository.upsert",
                new=AsyncMock(),
            ) as mock_upsert_event,
        ):
            execution = await service.execute(
                organization_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                connection=connection,
                project_id=None,
                model_id="gpt-4o",
                system_prompt=None,
                user_prompt="Hi",
                temperature=None,
                top_p=None,
                max_tokens=None,
            )

        assert execution.status == PlaygroundExecutionStatus.FAILED
        assert execution.error_message is not None
        assert "boom" in execution.error_message
        assert execution.usage_event_id is None
        mock_create.assert_awaited_once()
        mock_upsert_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_credential_decrypt_failure_is_captured_not_raised(self) -> None:
        session = AsyncMock()
        credentials = AsyncMock()
        credentials.decrypt = lambda _c: (_ for _ in ()).throw(ValueError("bad ciphertext"))
        service = PlaygroundService(session, credentials=credentials)
        connection = _connection()

        with patch(
            "app.repositories.playground_execution_repository.PlaygroundExecutionRepository.create",
            new=AsyncMock(side_effect=lambda x: x),
        ):
            execution = await service.execute(
                organization_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                connection=connection,
                project_id=None,
                model_id="gpt-4o",
                system_prompt=None,
                user_prompt="Hi",
                temperature=None,
                top_p=None,
                max_tokens=None,
            )

        assert execution.status == PlaygroundExecutionStatus.FAILED
        assert "bad ciphertext" in (execution.error_message or "")
