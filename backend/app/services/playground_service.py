"""PlaygroundService — EP-25.4 (AI Playground).

Every Playground request flows through the exact same pipeline every other
real usage-producing code path in this codebase already uses:

    ProviderConnection
          |
          v
    ProviderCredentialService.decrypt()    — same EP-22 service, the only
          |                                   place a plaintext key exists
          v
    build_provider_config()                — shared with ProviderValidator/
          |                                   ProviderSyncService (EP-22/23.3)
          v
    ProviderFactory(registry).create()     — the real adapter (EP-06)
          |
          v
    adapter.complete()                     — real HTTP call (EP-25.4 — the
          |                                   one new capability this EP adds
          |                                   to every adapter, see CLAUDE.md)
          v
    PricingEngine.calculate_cost()         — same EP-08 pricing engine
          |
          v
    UsageEventRepository.upsert() +
    UsageCostRecordRepository.upsert()     — the SAME tables/repositories
          |                                   UsageCollectionService writes,
          |                                   so this request is instantly
          |                                   real Analytics/Budgets/
          |                                   Dashboard data, never a
          |                                   parallel "playground usage"
          |                                   table
          v
    BudgetEvaluationService.evaluate_and_alert()  — same post-usage hook
                                                      ProviderSyncService's
                                                      manual-sync path calls

PlaygroundExecution (app.models.playground_execution) is the *only* new
table — it stores the prompt/response text and UI-facing history fields no
existing table stores. It is never read by Analytics/Budgets/Dashboard.

A failed request (bad key, provider error, network failure) never writes a
UsageEvent/UsageCostRecord — no provider charges for a failed call, so
Costorah doesn't record spend for one either. It still writes a
PlaygroundExecution row (status=FAILED) so the History panel shows what was
attempted and why it didn't work.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import uuid7
from app.models.playground_execution import PlaygroundExecution, PlaygroundExecutionStatus
from app.models.provider_connection import ProviderConnection
from app.models.usage_event import UsageEvent
from app.providers.factory import ProviderFactory
from app.providers.models import Message, MessageRole, ProviderRequest
from app.providers.registry import get_registry
from app.providers.validation import build_provider_config
from app.repositories.playground_execution_repository import PlaygroundExecutionRepository
from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
from app.repositories.usage_event_repository import UsageEventRepository
from app.services.provider_credential_service import ProviderCredentialService

log = structlog.get_logger(__name__)


class PlaygroundService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        credentials: ProviderCredentialService | None = None,
    ) -> None:
        self._session = session
        self._credentials = credentials or ProviderCredentialService()
        self._registry = get_registry()
        self._executions = PlaygroundExecutionRepository(session)

    async def execute(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        connection: ProviderConnection,
        project_id: uuid.UUID | None,
        model_id: str,
        system_prompt: str | None,
        user_prompt: str,
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
        comparison_group_id: uuid.UUID | None = None,
    ) -> PlaygroundExecution:
        """Run one prompt against one connection, persist real usage on
        success, and always persist a PlaygroundExecution history row.
        """
        logger = log.bind(
            organization_id=str(organization_id),
            connection_id=str(connection.id),
            provider=connection.provider_type.value,
            model=model_id,
        )

        execution = PlaygroundExecution()
        execution.id = uuid7()
        now = datetime.now(UTC)
        execution.created_at = now
        execution.updated_at = now
        execution.organization_id = organization_id
        execution.user_id = user_id
        execution.project_id = project_id
        execution.provider_connection_id = connection.id
        execution.provider = connection.provider_type.value
        execution.model = model_id
        execution.system_prompt = system_prompt
        execution.user_prompt = user_prompt
        execution.temperature = temperature
        execution.top_p = top_p
        execution.max_tokens = max_tokens
        execution.comparison_group_id = comparison_group_id
        execution.currency = "USD"

        started = time.monotonic()
        adapter = None
        try:
            api_key = (
                self._credentials.decrypt(connection.encrypted_api_key)
                if connection.encrypted_api_key
                else None
            )
            config = build_provider_config(
                connection.provider_type, api_key=api_key, base_url=connection.base_url
            )
            adapter = ProviderFactory(self._registry).create(config)

            messages = []
            if system_prompt:
                messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
            messages.append(Message(role=MessageRole.USER, content=user_prompt))
            extra: dict[str, Any] = {}
            if top_p is not None:
                extra["top_p"] = top_p
            request = ProviderRequest(
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                extra=extra,
            )
            response = await adapter.complete(request)
        except Exception as exc:
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            logger.warning(
                "playground_execution_failed", error_type=type(exc).__name__, latency_ms=latency_ms
            )
            execution.status = PlaygroundExecutionStatus.FAILED
            execution.latency_ms = latency_ms
            # Same discipline every provider adapter's own exception classes
            # already follow (app/providers/errors.py) — a normalized,
            # user-safe message, never the raw exception (which could carry
            # request headers or account-identifying detail).
            execution.error_message = str(exc)[:500]
            await self._executions.create(execution)
            return execution
        finally:
            if adapter is not None:
                await adapter.aclose()

        latency_ms = round((time.monotonic() - started) * 1000, 2)
        usage = response.usage
        execution.status = PlaygroundExecutionStatus.SUCCEEDED
        execution.latency_ms = latency_ms
        execution.response_text = response.content
        execution.prompt_tokens = usage.prompt_tokens if usage else 0
        execution.completion_tokens = usage.completion_tokens if usage else 0
        execution.total_tokens = usage.total_tokens if usage else 0

        usage_event = await self._record_usage(
            organization_id=organization_id,
            project_id=project_id,
            connection=connection,
            model_id=response.model_id or model_id,
            prompt_tokens=execution.prompt_tokens,
            completion_tokens=execution.completion_tokens,
            total_tokens=execution.total_tokens,
            cached_tokens=usage.cached_tokens if usage else None,
            execution_id=execution.id,
            timestamp=now,
        )
        if usage_event is not None:
            execution.usage_event_id = usage_event.id
            cost = await self._cost_for_event(usage_event)
            if cost is not None:
                execution.estimated_cost = cost["total_cost"]
                execution.currency = cost["currency"]

        await self._executions.create(execution)
        logger.info(
            "playground_execution_succeeded",
            latency_ms=latency_ms,
            total_tokens=execution.total_tokens,
        )
        return execution

    async def _record_usage(
        self,
        *,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None,
        connection: ProviderConnection,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cached_tokens: int | None,
        execution_id: uuid.UUID,
        timestamp: datetime,
    ) -> UsageEvent | None:
        """Write a real UsageEvent for this request — same table, same
        repository, every other real usage-producing path already writes
        to. ``provider_request_id`` is deterministic and namespaced
        (``playground:{execution_id}``) so it can never collide with an
        id a real background sync later imports for the same connection.
        """
        event = UsageEvent()
        event.id = uuid7()
        event.created_at = timestamp
        event.updated_at = timestamp
        event.organization_id = organization_id
        event.project_id = project_id
        event.provider_connection_id = connection.id
        event.collection_run_id = None
        event.provider = connection.provider_type.value
        event.provider_request_id = f"playground:{execution_id}"
        event.model = model_id
        event.timestamp = timestamp
        event.request_count = 1
        event.prompt_tokens = prompt_tokens
        event.completion_tokens = completion_tokens
        event.cached_tokens = cached_tokens
        event.total_tokens = total_tokens
        event.event_metadata = {"source": "playground"}
        event.raw_provider_payload = {}

        event_repo = UsageEventRepository(self._session)
        try:
            return await event_repo.upsert(event)
        except Exception:
            log.warning("playground_usage_event_write_failed", exc_info=True)
            return None

    async def _cost_for_event(self, event: UsageEvent) -> dict[str, Any] | None:
        """Best-effort cost attribution — mirrors UsageCollectionService's
        own `_process_page` pattern exactly (pricing may not exist for
        every model; a missing price is never a hard failure, just $0/None
        shown in the Playground UI with an honest 'no pricing configured'
        note, matching this codebase's no-fake-cost discipline)."""
        from app.models.usage_cost_record import UsageCostRecord as UsageCostRecordModel
        from app.pricing.engine import PricingEngine, PricingNotFoundError
        from app.repositories.model_pricing_repository import ModelPricingRepository

        pricing_repo = ModelPricingRepository(self._session)
        cost_repo = UsageCostRecordRepository(self._session)
        engine = PricingEngine(pricing_repo)

        usage_date = event.timestamp.date()
        try:
            cost_result = await engine.calculate_event_cost(event, usage_date)
        except PricingNotFoundError:
            return None

        now = datetime.now(UTC)
        record = UsageCostRecordModel()
        record.id = uuid7()
        record.created_at = now
        record.updated_at = now
        record.usage_event_id = event.id
        record.organization_id = event.organization_id
        record.project_id = event.project_id
        record.provider_connection_id = event.provider_connection_id
        record.model_pricing_id = cost_result["model_pricing_id"]
        record.provider = event.provider
        record.model = event.model
        record.currency = cost_result["currency"]
        record.usage_date = usage_date
        record.prompt_tokens = event.prompt_tokens
        record.completion_tokens = event.completion_tokens
        record.cached_tokens = event.cached_tokens
        record.total_tokens = event.total_tokens
        record.prompt_cost = cost_result["prompt_cost"]
        record.completion_cost = cost_result["completion_cost"]
        record.cached_cost = cost_result["cached_cost"]
        record.total_cost = cost_result["total_cost"]
        record.calculation_version = cost_result["calculation_version"]
        await cost_repo.upsert(record)
        return {
            "total_cost": Decimal(str(cost_result["total_cost"])),
            "currency": cost_result["currency"],
        }
