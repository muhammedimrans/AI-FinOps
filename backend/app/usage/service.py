"""Usage collection service — F-043 / F-044 (EP-08).

Orchestrates the full usage collection pipeline:

1. Create a ``UsageCollectionRun`` record.
2. Load the existing ``UsageCollectionCheckpoint`` (if any) to resume
   incremental collection from the last successful position.
3. Create a provider adapter via ``ProviderFactory(registry).create(config)``.
4. Paginate through the provider's usage API using ``adapter.get_usage()``.
5. Validate each ``NormalizedUsageEvent`` (skip invalid, log warning).
6. Upsert events idempotently (ON CONFLICT DO UPDATE on the dedup key).
7. Update the checkpoint after each page (mid-range resume support).
8. Mark the run ``completed`` (or ``failed`` on exception).

Design principles
-----------------
- Provider-agnostic: no provider-specific logic in this file.
- Idempotent: re-running for the same date range is safe.
- Incremental: subsequent runs only fetch new events since ``last_collected_at``.
- Checkpoint granularity: updated per page so interruption loses at most one page.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.models.provider_usage_summary import ProviderUsageSummary
from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint
from app.models.usage_collection_run import CollectionRunStatus, CollectionTrigger, UsageCollectionRun
from app.models.usage_event import UsageEvent
from app.providers.config import (
    AnthropicConfig,
    OpenAIConfig,
    SecretReference,
    SecretStoreType,
)
from app.providers.errors import ProviderError
from app.providers.factory import ProviderFactory
from app.providers.models import NormalizedUsageEvent, UsagePage
from app.providers.registry import get_registry
from app.usage.validator import UsageEventValidator, UsageValidationError

log = structlog.get_logger(__name__)


# ── Config builders ────────────────────────────────────────────────────────────


def _build_config(provider: str) -> OpenAIConfig | AnthropicConfig:
    """Build a provider config using the standard ENV-var key reference."""
    match provider:
        case "openai":
            return OpenAIConfig(
                provider_type="openai",
                display_name="OpenAI",
                api_key_ref=SecretReference(
                    secret_store=SecretStoreType.ENV,
                    secret_key="OPENAI_API_KEY",
                ),
            )
        case "anthropic":
            return AnthropicConfig(
                provider_type="anthropic",
                display_name="Anthropic",
                api_key_ref=SecretReference(
                    secret_store=SecretStoreType.ENV,
                    secret_key="ANTHROPIC_API_KEY",
                ),
            )
        case _:
            raise ValueError(f"No config builder for provider {provider!r}")


# ── Repository helpers (inline to keep service self-contained) ─────────────────
# The service imports repos lazily to avoid circular imports at module load time.


class UsageCollectionService:
    """Orchestrates incremental usage collection for one provider.

    Parameters
    ----------
    session:
        An ``AsyncSession`` scoped to the current request / task.  The caller
        is responsible for committing and closing the session.
    registry:
        Optional ``ProviderRegistry`` override (primarily for testing).
    page_limit:
        Maximum number of events requested per API page.
    """

    def __init__(
        self,
        session: Any,
        *,
        registry: Any | None = None,
        page_limit: int = 100,
    ) -> None:
        self._session = session
        self._registry = registry or get_registry()
        self._page_limit = page_limit
        self._validator = UsageEventValidator()

    # ── Public API ─────────────────────────────────────────────────────────────

    async def collect(
        self,
        *,
        organization_id: uuid.UUID,
        provider: str,
        start_date: datetime,
        end_date: datetime,
        provider_connection_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        triggered_by: CollectionTrigger = CollectionTrigger.MANUAL,
    ) -> UsageCollectionRun:
        """Run a full collection pass for the given provider and date range.

        Returns the completed (or failed) ``UsageCollectionRun`` record.
        The caller must commit the session after this method returns.
        """
        from app.repositories.usage_collection_checkpoint_repository import (
            UsageCollectionCheckpointRepository,
        )
        from app.repositories.usage_collection_run_repository import UsageCollectionRunRepository
        from app.repositories.usage_event_repository import UsageEventRepository

        run_repo = UsageCollectionRunRepository(self._session)
        event_repo = UsageEventRepository(self._session)
        checkpoint_repo = UsageCollectionCheckpointRepository(self._session)

        logger = log.bind(
            organization_id=str(organization_id),
            provider=provider,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        # ── 1. Create run ──────────────────────────────────────────────────────
        run = UsageCollectionRun()
        run.organization_id = organization_id
        run.provider_connection_id = provider_connection_id
        run.provider = provider
        run.status = CollectionRunStatus.RUNNING
        run.triggered_by = triggered_by
        run.started_at = datetime.now(UTC)
        run.collection_start = start_date
        run.collection_end = end_date
        run.collection_config = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        run = await run_repo.create(run)
        logger = logger.bind(run_id=str(run.id))
        logger.info("usage_collection_run_started")

        try:
            # ── 2. Load checkpoint ─────────────────────────────────────────────
            checkpoint = await checkpoint_repo.get_by_org_provider(
                organization_id, provider, provider_connection_id
            )
            effective_start = start_date
            if checkpoint and checkpoint.last_collected_at > start_date:
                effective_start = checkpoint.last_collected_at
            cursor: str | None = checkpoint.cursor if checkpoint else None

            # ── 3. Build adapter ───────────────────────────────────────────────
            config = _build_config(provider)
            adapter = ProviderFactory(self._registry).create(config)

            # ── 4. Paginate ────────────────────────────────────────────────────
            total_events = 0
            total_failed = 0
            pages = 0

            while True:
                page: UsagePage = await adapter.get_usage(
                    effective_start,
                    end_date,
                    cursor=cursor,
                    limit=self._page_limit,
                )
                pages += 1

                # ── 5. Validate + upsert events ────────────────────────────────
                created, failed = await self._process_page(
                    page.events,
                    organization_id=organization_id,
                    project_id=project_id,
                    provider_connection_id=provider_connection_id,
                    collection_run_id=run.id,
                    event_repo=event_repo,
                )
                total_events += created
                total_failed += failed

                # ── 6. Update checkpoint ───────────────────────────────────────
                new_cursor = page.next_cursor if page.has_more else None
                checkpoint = await checkpoint_repo.upsert(
                    organization_id=organization_id,
                    provider=provider,
                    provider_connection_id=provider_connection_id,
                    last_collected_at=end_date if not page.has_more else effective_start,
                    cursor=new_cursor,
                    last_run_id=run.id,
                )

                logger.info(
                    "usage_page_processed",
                    page=pages,
                    events_created=created,
                    events_failed=failed,
                    has_more=page.has_more,
                )

                if not page.has_more:
                    break
                cursor = page.next_cursor

            # ── 7. Mark completed ──────────────────────────────────────────────
            run = await run_repo.update(
                run,
                status=CollectionRunStatus.COMPLETED,
                completed_at=datetime.now(UTC),
                events_collected=total_events,
                events_failed=total_failed,
                pages_fetched=pages,
            )
            logger.info(
                "usage_collection_run_completed",
                events_collected=total_events,
                events_failed=total_failed,
                pages=pages,
            )

        except Exception as exc:
            logger.warning("usage_collection_run_failed", error=str(exc))
            run = await run_repo.update(
                run,
                status=CollectionRunStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )
            raise

        return run

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _process_page(
        self,
        events: list[NormalizedUsageEvent],
        *,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None,
        provider_connection_id: uuid.UUID | None,
        collection_run_id: uuid.UUID,
        event_repo: Any,
    ) -> tuple[int, int]:
        """Validate and upsert a page of events.

        Returns ``(created_count, failed_count)``.
        """
        created = 0
        failed = 0

        for norm_event in events:
            try:
                self._validator.validate(norm_event)
            except UsageValidationError as exc:
                log.warning(
                    "usage_event_validation_failed",
                    provider_request_id=norm_event.provider_request_id,
                    error=str(exc),
                )
                failed += 1
                continue

            orm_event = _build_orm_event(
                norm_event,
                organization_id=organization_id,
                project_id=project_id,
                provider_connection_id=provider_connection_id,
                collection_run_id=collection_run_id,
            )
            await event_repo.upsert(orm_event)
            created += 1

        return created, failed


def _build_orm_event(
    norm: NormalizedUsageEvent,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID | None,
    provider_connection_id: uuid.UUID | None,
    collection_run_id: uuid.UUID,
) -> UsageEvent:
    """Convert a NormalizedUsageEvent to a UsageEvent ORM instance."""
    event = UsageEvent()
    event.organization_id = organization_id
    event.project_id = project_id
    event.provider_connection_id = provider_connection_id
    event.collection_run_id = collection_run_id
    event.provider = norm.provider
    event.provider_request_id = norm.provider_request_id
    event.model = norm.model
    event.timestamp = norm.timestamp
    event.request_count = norm.request_count
    event.prompt_tokens = norm.prompt_tokens
    event.completion_tokens = norm.completion_tokens
    event.cached_tokens = norm.cached_tokens
    event.total_tokens = norm.total_tokens
    event.event_metadata = norm.metadata
    event.raw_provider_payload = norm.raw_payload
    return event
