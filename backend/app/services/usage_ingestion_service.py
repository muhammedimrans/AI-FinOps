"""
UsageIngestionService — business logic for POST /v1/ingest/usage (EP-16).

Responsibilities: validate ownership, deduplicate by request_id, persist the
UsageRecord (the source of truth for this API), and — best-effort — feed the
existing EP-08/EP-09 tables (UsageEvent, UsageCostRecord, DailyCostSummary)
so the dashboard/analytics endpoints built in EP-10/EP-11 reflect ingested
usage immediately, with no endpoint or frontend changes.

Cost is caller-reported, not computed by PricingEngine: the whole point of
this endpoint is accepting a value the caller already knows (their own
provider bill), which is more authoritative than our price catalog and
doesn't require every ingested provider/model to have a catalog entry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.aggregation import AggregationService
from app.db.mixins import uuid7
from app.models.organization import Organization
from app.models.usage_cost_record import UsageCostRecord
from app.models.usage_event import UsageEvent
from app.models.usage_record import UsageRecord, UsageRecordStatus
from app.repositories.project_repository import ProjectRepository
from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
from app.repositories.usage_event_repository import UsageEventRepository
from app.repositories.usage_record_repository import UsageRecordRepository
from app.schemas.usage_ingestion import IngestUsageRequest


class UnknownProjectError(ValueError):
    """The requested project_id does not exist, or belongs to another organization."""


def _split_cost(
    total_cost: Decimal, input_tokens: int, output_tokens: int
) -> tuple[Decimal, Decimal]:
    """
    Approximate a prompt/completion split of a caller-reported total cost.

    The ingestion payload only carries one aggregate `cost` figure — there is
    no authoritative split. Token-count-weighted proportion is a documented
    estimate (not a measurement) purely so the existing prompt/completion
    breakdown fields on UsageCostRecord/DailyCostSummary have a non-degenerate
    value; `total_cost` (the caller-reported figure) remains the source of
    truth everywhere spend is actually totaled.
    """
    total = input_tokens + output_tokens
    if total <= 0:
        return Decimal("0"), total_cost
    prompt_share = (total_cost * input_tokens / total).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )
    completion_share = total_cost - prompt_share
    return prompt_share, completion_share


class UsageIngestionService:
    """Orchestrates validation, deduplication, storage, and aggregation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._usage_repo = UsageRecordRepository(session)
        self._project_repo = ProjectRepository(session)

    async def ingest(
        self,
        *,
        organization: Organization,
        api_key_id: uuid.UUID | None,
        payload: IngestUsageRequest,
    ) -> tuple[UsageRecord, bool]:
        """
        Validate, deduplicate, and store one usage record.

        Returns (record, is_duplicate). Raises UnknownProjectError if
        payload.project_id doesn't belong to `organization`.
        """
        existing = await self._usage_repo.get_by_request_id(organization.id, payload.request_id)
        if existing is not None:
            return existing, True

        if payload.project_id is not None:
            project = await self._project_repo.get(payload.project_id)
            if project is None or project.organization_id != organization.id:
                raise UnknownProjectError(str(payload.project_id))

        record = self._build_record(
            organization_id=organization.id,
            api_key_id=api_key_id,
            payload=payload,
        )

        try:
            created = await self._usage_repo.create(record)
        except IntegrityError:
            # Concurrent request won the race on (organization_id, request_id) —
            # the unique constraint, not this check, is the real guarantee.
            await self._session.rollback()
            existing = await self._usage_repo.get_by_request_id(organization.id, payload.request_id)
            if existing is not None:
                return existing, True
            raise

        await self._feed_dashboard_aggregates(created, organization_id=organization.id)

        return created, False

    @staticmethod
    def _build_record(
        *,
        organization_id: uuid.UUID,
        api_key_id: uuid.UUID | None,
        payload: IngestUsageRequest,
    ) -> UsageRecord:
        now = datetime.now(UTC)
        record = UsageRecord()
        record.id = uuid7()
        record.organization_id = organization_id
        record.project_id = payload.project_id
        record.api_key_id = api_key_id
        record.provider = payload.provider
        record.model = payload.model
        record.request_id = payload.request_id
        record.status = UsageRecordStatus(payload.status)
        record.input_tokens = payload.input_tokens
        record.output_tokens = payload.output_tokens
        record.cached_tokens = payload.cached_tokens
        record.total_tokens = payload.resolved_total_tokens
        record.cost = payload.cost
        record.currency = payload.currency
        record.latency_ms = payload.latency_ms
        record.region = payload.region
        record.usage_metadata = payload.metadata
        record.ingested_at = now
        record.request_timestamp = payload.resolved_timestamp
        return record

    async def _feed_dashboard_aggregates(
        self,
        record: UsageRecord,
        *,
        organization_id: uuid.UUID,
    ) -> None:
        """
        Write into the tables the existing dashboard/analytics endpoints
        already read (UsageEvent, UsageCostRecord, DailyCostSummary), so
        ingested usage shows up immediately with zero endpoint or frontend
        changes.

        Deliberately NOT best-effort / exception-swallowing: this runs in
        the same transaction as the UsageRecord insert above (get_db()
        commits once, at the end of the request). If any write here fails,
        letting the exception propagate rolls back the *entire* transaction
        — including the UsageRecord — rather than silently committing a
        UsageRecord with no matching dashboard data. That's the safe choice
        specifically because ingestion is idempotent: a caller who retries
        after a 500 will either succeed cleanly or hit the same failure
        again, never double-count (the (organization_id, request_id)
        constraint doesn't care how many times it's retried).
        """
        event_repo = UsageEventRepository(self._session)
        orm_event = UsageEvent()
        orm_event.id = uuid7()
        orm_event.organization_id = organization_id
        orm_event.project_id = record.project_id
        orm_event.provider_connection_id = None
        orm_event.collection_run_id = None
        orm_event.provider = record.provider
        orm_event.provider_request_id = record.request_id
        orm_event.model = record.model
        orm_event.timestamp = record.request_timestamp
        orm_event.request_count = 1
        orm_event.prompt_tokens = record.input_tokens
        orm_event.completion_tokens = record.output_tokens
        orm_event.cached_tokens = record.cached_tokens
        orm_event.total_tokens = record.total_tokens
        orm_event.event_metadata = record.usage_metadata
        orm_event.raw_provider_payload = {}
        await event_repo.upsert(orm_event)

        usage_date = record.request_timestamp.date()
        prompt_cost, completion_cost = _split_cost(
            record.cost, record.input_tokens, record.output_tokens
        )

        cost_record = UsageCostRecord()
        cost_record.id = uuid7()
        cost_record.usage_event_id = orm_event.id
        cost_record.organization_id = organization_id
        cost_record.project_id = record.project_id
        cost_record.provider_connection_id = None
        cost_record.model_pricing_id = None
        cost_record.provider = record.provider
        cost_record.model = record.model
        cost_record.currency = record.currency
        cost_record.usage_date = usage_date
        cost_record.prompt_tokens = record.input_tokens
        cost_record.completion_tokens = record.output_tokens
        cost_record.cached_tokens = record.cached_tokens
        cost_record.total_tokens = record.total_tokens
        cost_record.prompt_cost = prompt_cost
        cost_record.completion_cost = completion_cost
        cost_record.cached_cost = None
        cost_record.total_cost = record.cost
        cost_record.calculation_version = "ep16-reported"
        await UsageCostRecordRepository(self._session).upsert(cost_record)

        # Bounded to this one organization+day — never a full-table scan.
        await AggregationService(self._session).build_daily_summaries(organization_id, usage_date)
