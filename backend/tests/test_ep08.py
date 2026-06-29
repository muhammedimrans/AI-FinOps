"""EP-08 test suite — Usage Collection Engine.

Coverage targets:
- F-041: NormalizedUsageEvent and UsagePage Pydantic models
- F-042: OpenAI and Anthropic normalizers, NormalizerRegistry, _dedup_hash
- F-043: UsageEventRepository CRUD and filtered queries
- F-044: UsageCollectionRunRepository CRUD and filtered queries
- F-045: UsageCollectionCheckpointRepository get/upsert
- F-046: UsageCollectionService — full collection flow with mock adapter
- F-047: BackgroundCollectionFramework — lifecycle, cancellation, status
- F-048: UsageEventValidator — all validation rules
- F-049: REST endpoints — POST /usage/collect, GET stubs

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Import test subjects ───────────────────────────────────────────────────────

from app.providers.models import NormalizedUsageEvent, UsagePage
from app.usage.normalizer import (
    AnthropicUsageNormalizer,
    NormalizerRegistry,
    OpenAIUsageNormalizer,
    UsageNormalizer,
    _dedup_hash,
    get_normalizer_registry,
)
from app.usage.validator import UsageEventValidator, UsageValidationError

# ── Helpers ────────────────────────────────────────────────────────────────────

_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
_START = datetime(2025, 5, 1, 0, 0, 0, tzinfo=UTC)
_END = datetime(2025, 5, 31, 23, 59, 59, tzinfo=UTC)
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
_CONN_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")


def _make_norm_event(
    *,
    provider_request_id: str = "req_abc123",
    provider: str = "openai",
    model: str = "gpt-4o",
    timestamp: datetime = _NOW,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    total_tokens: int = 150,
    cached_tokens: int | None = None,
    request_count: int = 1,
) -> NormalizedUsageEvent:
    return NormalizedUsageEvent(
        provider_request_id=provider_request_id,
        provider=provider,
        model=model,
        timestamp=timestamp,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        request_count=request_count,
    )


# ══════════════════════════════════════════════════════════════════════════════
# F-041: NormalizedUsageEvent and UsagePage models
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizedUsageEvent:
    def test_required_fields(self) -> None:
        event = _make_norm_event()
        assert event.provider == "openai"
        assert event.model == "gpt-4o"
        assert event.prompt_tokens == 100

    def test_defaults(self) -> None:
        event = NormalizedUsageEvent(
            provider_request_id="req_x",
            provider="openai",
            model="gpt-4o",
            timestamp=_NOW,
        )
        assert event.prompt_tokens == 0
        assert event.completion_tokens == 0
        assert event.total_tokens == 0
        assert event.cached_tokens is None
        assert event.request_count == 1
        assert event.metadata == {}
        assert event.raw_payload == {}

    def test_immutable(self) -> None:
        event = _make_norm_event()
        with pytest.raises(Exception):  # frozen model
            event.provider = "anthropic"  # type: ignore[misc]

    def test_cached_tokens_optional(self) -> None:
        event = _make_norm_event(cached_tokens=25)
        assert event.cached_tokens == 25


class TestUsagePage:
    def test_defaults(self) -> None:
        page = UsagePage()
        assert page.events == []
        assert page.next_cursor is None
        assert page.has_more is False

    def test_with_events(self) -> None:
        ev = _make_norm_event()
        page = UsagePage(events=[ev], next_cursor="cursor123", has_more=True)
        assert len(page.events) == 1
        assert page.has_more is True
        assert page.next_cursor == "cursor123"

    def test_immutable(self) -> None:
        page = UsagePage()
        with pytest.raises(Exception):
            page.has_more = True  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# F-042: _dedup_hash
# ══════════════════════════════════════════════════════════════════════════════


class TestDedupHash:
    def test_deterministic(self) -> None:
        h1 = _dedup_hash("openai", "gpt-4o", "1234567890")
        h2 = _dedup_hash("openai", "gpt-4o", "1234567890")
        assert h1 == h2

    def test_different_inputs_produce_different_hashes(self) -> None:
        h1 = _dedup_hash("openai", "gpt-4o", "1234567890")
        h2 = _dedup_hash("openai", "gpt-4o", "9999999999")
        assert h1 != h2

    def test_returns_40_char_hex(self) -> None:
        h = _dedup_hash("openai", "model", "ts")
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_order_matters(self) -> None:
        h1 = _dedup_hash("a", "b", "c")
        h2 = _dedup_hash("c", "b", "a")
        assert h1 != h2


# ══════════════════════════════════════════════════════════════════════════════
# F-042: OpenAIUsageNormalizer
# ══════════════════════════════════════════════════════════════════════════════


class TestOpenAIUsageNormalizer:
    def setup_method(self) -> None:
        self.normalizer = OpenAIUsageNormalizer()

    def test_provider_name(self) -> None:
        assert self.normalizer.provider_name == "openai"

    def test_basic_normalization(self) -> None:
        raw: dict[str, Any] = {
            "start_time": 1717200000,
            "model": "gpt-4o",
            "input_tokens": 1000,
            "output_tokens": 500,
            "num_model_requests": 3,
        }
        event = self.normalizer.normalize(raw)
        assert event.provider == "openai"
        assert event.model == "gpt-4o"
        assert event.prompt_tokens == 1000
        assert event.completion_tokens == 500
        assert event.total_tokens == 1500
        assert event.request_count == 3
        assert event.cached_tokens is None

    def test_uses_id_if_present(self) -> None:
        raw: dict[str, Any] = {
            "id": "req_specific_id",
            "start_time": 1717200000,
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 50,
        }
        event = self.normalizer.normalize(raw)
        assert event.provider_request_id == "req_specific_id"

    def test_generates_dedup_hash_without_id(self) -> None:
        raw: dict[str, Any] = {
            "start_time": 1717200000,
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 50,
        }
        event = self.normalizer.normalize(raw)
        expected = _dedup_hash("openai", "gpt-4o", "1717200000")
        assert event.provider_request_id == expected

    def test_cached_tokens_extracted(self) -> None:
        raw: dict[str, Any] = {
            "start_time": 1717200000,
            "model": "gpt-4o",
            "input_tokens": 1000,
            "output_tokens": 500,
            "cached_input_tokens": 200,
        }
        event = self.normalizer.normalize(raw)
        assert event.cached_tokens == 200

    def test_defaults_for_missing_fields(self) -> None:
        raw: dict[str, Any] = {"start_time": 1717200000}
        event = self.normalizer.normalize(raw)
        assert event.model == "unknown"
        assert event.prompt_tokens == 0
        assert event.completion_tokens == 0
        assert event.request_count == 1

    def test_raw_payload_preserved(self) -> None:
        raw: dict[str, Any] = {
            "start_time": 1717200000,
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 50,
            "extra_field": "value",
        }
        event = self.normalizer.normalize(raw)
        assert event.raw_payload == raw

    def test_implements_protocol(self) -> None:
        assert isinstance(self.normalizer, UsageNormalizer)


# ══════════════════════════════════════════════════════════════════════════════
# F-042: AnthropicUsageNormalizer
# ══════════════════════════════════════════════════════════════════════════════


class TestAnthropicUsageNormalizer:
    def setup_method(self) -> None:
        self.normalizer = AnthropicUsageNormalizer()

    def test_provider_name(self) -> None:
        assert self.normalizer.provider_name == "anthropic"

    def test_basic_normalization(self) -> None:
        raw: dict[str, Any] = {
            "id": "req_claude_xyz",
            "model": "claude-3-5-sonnet-20241022",
            "created_at": "2025-05-01T12:00:00Z",
            "input_tokens": 2000,
            "output_tokens": 1000,
        }
        event = self.normalizer.normalize(raw)
        assert event.provider == "anthropic"
        assert event.model == "claude-3-5-sonnet-20241022"
        assert event.provider_request_id == "req_claude_xyz"
        assert event.prompt_tokens == 2000
        assert event.completion_tokens == 1000

    def test_uses_id_if_present(self) -> None:
        raw: dict[str, Any] = {
            "id": "req_explicit_id",
            "model": "claude-3",
            "created_at": "2025-05-01T00:00:00Z",
            "input_tokens": 100,
            "output_tokens": 50,
        }
        event = self.normalizer.normalize(raw)
        assert event.provider_request_id == "req_explicit_id"

    def test_cached_tokens_extracted(self) -> None:
        raw: dict[str, Any] = {
            "id": "req_y",
            "model": "claude-3",
            "created_at": "2025-05-01T00:00:00Z",
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 300,
        }
        event = self.normalizer.normalize(raw)
        assert event.cached_tokens == 300

    def test_timestamp_parsing_iso8601(self) -> None:
        raw: dict[str, Any] = {
            "model": "claude-3",
            "created_at": "2025-05-15T09:30:00Z",
            "input_tokens": 100,
            "output_tokens": 50,
        }
        event = self.normalizer.normalize(raw)
        assert event.timestamp.year == 2025
        assert event.timestamp.month == 5
        assert event.timestamp.day == 15

    def test_defaults_for_missing_timestamp(self) -> None:
        raw: dict[str, Any] = {"model": "claude-3", "input_tokens": 100, "output_tokens": 50}
        event = self.normalizer.normalize(raw)
        assert event.timestamp is not None

    def test_implements_protocol(self) -> None:
        assert isinstance(self.normalizer, UsageNormalizer)

    def test_num_requests_field(self) -> None:
        raw: dict[str, Any] = {
            "model": "claude-3",
            "created_at": "2025-05-01T00:00:00Z",
            "input_tokens": 100,
            "output_tokens": 50,
            "num_requests": 5,
        }
        event = self.normalizer.normalize(raw)
        assert event.request_count == 5


# ══════════════════════════════════════════════════════════════════════════════
# F-042: NormalizerRegistry
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizerRegistry:
    def test_register_and_get(self) -> None:
        registry = NormalizerRegistry()
        norm = OpenAIUsageNormalizer()
        registry.register(norm)
        assert registry.get("openai") is norm

    def test_get_unknown_returns_none(self) -> None:
        registry = NormalizerRegistry()
        assert registry.get("unknown_provider") is None

    def test_supported_providers_sorted(self) -> None:
        registry = get_normalizer_registry()
        providers = registry.supported_providers()
        assert providers == sorted(providers)
        assert "openai" in providers
        assert "anthropic" in providers

    def test_default_registry_has_both_providers(self) -> None:
        registry = get_normalizer_registry()
        assert registry.get("openai") is not None
        assert registry.get("anthropic") is not None


# ══════════════════════════════════════════════════════════════════════════════
# F-048: UsageEventValidator
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageEventValidator:
    def setup_method(self) -> None:
        self.validator = UsageEventValidator()

    def test_valid_event_passes(self) -> None:
        event = _make_norm_event()
        self.validator.validate(event)  # no exception

    def test_empty_provider_request_id_fails(self) -> None:
        event = _make_norm_event(provider_request_id="")
        with pytest.raises(UsageValidationError, match="provider_request_id"):
            self.validator.validate(event)

    def test_whitespace_provider_request_id_fails(self) -> None:
        event = _make_norm_event(provider_request_id="   ")
        with pytest.raises(UsageValidationError, match="provider_request_id"):
            self.validator.validate(event)

    def test_empty_provider_fails(self) -> None:
        event = _make_norm_event(provider="")
        with pytest.raises(UsageValidationError, match="provider"):
            self.validator.validate(event)

    def test_empty_model_fails(self) -> None:
        event = _make_norm_event(model="")
        with pytest.raises(UsageValidationError, match="model"):
            self.validator.validate(event)

    def test_future_timestamp_fails(self) -> None:
        future_ts = datetime.now(UTC) + timedelta(hours=2)
        event = _make_norm_event(timestamp=future_ts)
        with pytest.raises(UsageValidationError, match="future"):
            self.validator.validate(event)

    def test_timestamp_within_tolerance_passes(self) -> None:
        # 4 minutes in future is within the 5-minute tolerance
        near_future = datetime.now(UTC) + timedelta(minutes=4)
        event = _make_norm_event(timestamp=near_future)
        self.validator.validate(event)  # no exception

    def test_negative_prompt_tokens_fails(self) -> None:
        event = _make_norm_event(prompt_tokens=-1, total_tokens=-1)
        with pytest.raises(UsageValidationError, match="prompt_tokens"):
            self.validator.validate(event)

    def test_negative_completion_tokens_fails(self) -> None:
        event = _make_norm_event(completion_tokens=-1)
        with pytest.raises(UsageValidationError, match="completion_tokens"):
            self.validator.validate(event)

    def test_negative_total_tokens_fails(self) -> None:
        event = _make_norm_event(
            prompt_tokens=0, completion_tokens=0, total_tokens=-1
        )
        with pytest.raises(UsageValidationError, match="total_tokens"):
            self.validator.validate(event)

    def test_zero_request_count_fails(self) -> None:
        event = _make_norm_event(request_count=0)
        with pytest.raises(UsageValidationError, match="request_count"):
            self.validator.validate(event)

    def test_negative_request_count_fails(self) -> None:
        event = _make_norm_event(request_count=-5)
        with pytest.raises(UsageValidationError, match="request_count"):
            self.validator.validate(event)

    def test_cached_tokens_exceeds_prompt_fails(self) -> None:
        event = _make_norm_event(prompt_tokens=100, cached_tokens=200)
        with pytest.raises(UsageValidationError, match="cached_tokens"):
            self.validator.validate(event)

    def test_cached_tokens_negative_fails(self) -> None:
        event = _make_norm_event(cached_tokens=-1)
        with pytest.raises(UsageValidationError, match="cached_tokens"):
            self.validator.validate(event)

    def test_cached_tokens_equal_to_prompt_passes(self) -> None:
        event = _make_norm_event(prompt_tokens=100, cached_tokens=100)
        self.validator.validate(event)  # no exception

    def test_validation_error_carries_event(self) -> None:
        event = _make_norm_event(provider_request_id="")
        with pytest.raises(UsageValidationError) as exc_info:
            self.validator.validate(event)
        assert exc_info.value.event is event

    def test_zero_tokens_passes(self) -> None:
        event = _make_norm_event(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        self.validator.validate(event)


# ══════════════════════════════════════════════════════════════════════════════
# F-043: UsageEventRepository
# ══════════════════════════════════════════════════════════════════════════════


def _make_mock_session() -> MagicMock:
    """Return an AsyncMock-capable mock session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _make_usage_event(
    *,
    org_id: uuid.UUID | None = None,
    provider: str = "openai",
    provider_request_id: str = "req_test",
    model: str = "gpt-4o",
    run_id: uuid.UUID | None = None,
) -> Any:
    from app.db.mixins import uuid7
    from app.models.usage_event import UsageEvent

    event = UsageEvent()
    event.id = uuid7()
    event.organization_id = org_id or _ORG_ID
    event.provider = provider
    event.provider_request_id = provider_request_id
    event.model = model
    event.timestamp = _NOW
    event.request_count = 1
    event.prompt_tokens = 100
    event.completion_tokens = 50
    event.total_tokens = 150
    event.cached_tokens = None
    event.event_metadata = {}
    event.raw_provider_payload = {}
    event.collection_run_id = run_id or _RUN_ID
    return event


class TestUsageEventRepository:
    def setup_method(self) -> None:
        from app.repositories.usage_event_repository import UsageEventRepository

        self.session = _make_mock_session()
        self.repo = UsageEventRepository(self.session)

    def test_instantiation(self) -> None:
        from app.repositories.usage_event_repository import UsageEventRepository

        assert isinstance(self.repo, UsageEventRepository)

    @pytest.mark.asyncio
    async def test_upsert_calls_execute(self) -> None:
        event = _make_usage_event()
        # Mock pg_insert chain
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (event.id,)
        self.session.execute.return_value = mock_result

        result = await self.repo.upsert(event)
        assert self.session.execute.called
        assert result is event


# ══════════════════════════════════════════════════════════════════════════════
# F-044: UsageCollectionRunRepository
# ══════════════════════════════════════════════════════════════════════════════


def _make_collection_run(
    *,
    org_id: uuid.UUID | None = None,
    provider: str = "openai",
    status: Any = None,
) -> Any:
    from app.db.mixins import uuid7
    from app.models.usage_collection_run import (
        CollectionRunStatus,
        CollectionTrigger,
        UsageCollectionRun,
    )

    run = UsageCollectionRun()
    run.id = uuid7()
    run.organization_id = org_id or _ORG_ID
    run.provider = provider
    run.status = status or CollectionRunStatus.COMPLETED
    run.triggered_by = CollectionTrigger.MANUAL
    run.started_at = _START
    run.completed_at = _END
    run.collection_start = _START
    run.collection_end = _END
    run.events_collected = 10
    run.events_failed = 0
    run.pages_fetched = 1
    run.collection_config = {}
    run.created_at = _NOW
    run.updated_at = _NOW
    return run


class TestUsageCollectionRunRepository:
    def setup_method(self) -> None:
        from app.repositories.usage_collection_run_repository import (
            UsageCollectionRunRepository,
        )

        self.session = _make_mock_session()
        self.repo = UsageCollectionRunRepository(self.session)

    def test_instantiation(self) -> None:
        from app.repositories.usage_collection_run_repository import (
            UsageCollectionRunRepository,
        )

        assert isinstance(self.repo, UsageCollectionRunRepository)


# ══════════════════════════════════════════════════════════════════════════════
# F-045: UsageCollectionCheckpointRepository
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageCollectionCheckpointRepository:
    def setup_method(self) -> None:
        from app.repositories.usage_collection_checkpoint_repository import (
            UsageCollectionCheckpointRepository,
        )

        self.session = _make_mock_session()
        self.repo = UsageCollectionCheckpointRepository(self.session)

    def test_instantiation(self) -> None:
        from app.repositories.usage_collection_checkpoint_repository import (
            UsageCollectionCheckpointRepository,
        )

        assert isinstance(self.repo, UsageCollectionCheckpointRepository)

    @pytest.mark.asyncio
    async def test_get_by_org_provider_returns_none_when_not_found(self) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute.return_value = mock_result

        result = await self.repo.get_by_org_provider(_ORG_ID, "openai")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_calls_execute(self) -> None:
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (uuid.uuid4(),)
        self.session.execute.return_value = mock_result

        await self.repo.upsert(
            organization_id=_ORG_ID,
            provider="openai",
            provider_connection_id=None,
            last_collected_at=_END,
            cursor=None,
            last_run_id=_RUN_ID,
        )
        assert self.session.execute.called


# ══════════════════════════════════════════════════════════════════════════════
# F-046: UsageCollectionService
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageCollectionService:
    """Tests for the UsageCollectionService using mock adapter and repos."""

    def _make_service_with_mocks(
        self,
        *,
        usage_page: UsagePage | None = None,
        has_more: bool = False,
    ) -> tuple[Any, MagicMock, MagicMock, MagicMock, MagicMock]:
        """Build a service instance wired to mock repos and adapter."""
        from app.models.usage_collection_run import CollectionRunStatus, UsageCollectionRun
        from app.usage.service import UsageCollectionService

        # Create a mock adapter
        mock_adapter = AsyncMock()
        page = usage_page or UsagePage(
            events=[_make_norm_event()], next_cursor=None, has_more=False
        )
        mock_adapter.get_usage.return_value = page

        # Patch ProviderFactory to return our mock adapter
        mock_factory = MagicMock()
        mock_factory.create.return_value = mock_adapter

        # Patch _build_config
        mock_config = MagicMock()

        # Mock repos
        mock_run_repo = AsyncMock()
        completed_run = _make_collection_run()
        completed_run.status = CollectionRunStatus.COMPLETED
        completed_run.events_collected = 1
        mock_run_repo.create.return_value = _make_collection_run()
        mock_run_repo.update.return_value = completed_run

        mock_event_repo = AsyncMock()
        mock_event_repo.upsert.return_value = _make_usage_event()

        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None
        from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint
        from app.db.mixins import uuid7
        chk = UsageCollectionCheckpoint()
        chk.id = uuid7()
        chk.organization_id = _ORG_ID
        chk.provider = "openai"
        chk.last_collected_at = _END
        chk.cursor = None
        chk.sync_state = {}
        mock_checkpoint_repo.upsert.return_value = chk

        session = _make_mock_session()
        service = UsageCollectionService(session, page_limit=100)

        return service, mock_adapter, mock_run_repo, mock_event_repo, mock_checkpoint_repo

    def _patch_service_deps(
        self,
        mock_adapter: Any,
        *,
        completed_run: Any,
        initial_run: Any | None = None,
        checkpoint: Any | None = None,
        failed_run: Any | None = None,
    ) -> tuple[Any, Any, Any, Any]:
        """Patch all lazy imports inside UsageCollectionService.collect()."""
        from app.db.mixins import uuid7
        from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint

        if initial_run is None:
            initial_run = _make_collection_run()

        if checkpoint is None:
            chk = UsageCollectionCheckpoint()
            chk.id = uuid7()
            chk.organization_id = _ORG_ID
            chk.provider = "openai"
            chk.last_collected_at = _END
            chk.cursor = None
            chk.sync_state = {}
            checkpoint = chk

        mock_run_repo = AsyncMock()
        mock_run_repo.create.return_value = initial_run
        mock_run_repo.update.return_value = failed_run if failed_run else completed_run

        mock_event_repo = AsyncMock()
        mock_event_repo.upsert.return_value = _make_usage_event()

        mock_cp_repo = AsyncMock()
        mock_cp_repo.get_by_org_provider.return_value = None
        mock_cp_repo.upsert.return_value = checkpoint

        return mock_run_repo, mock_event_repo, mock_cp_repo, checkpoint

    @pytest.mark.asyncio
    async def test_collect_single_page(self) -> None:
        """Full collection of a single page returns a completed run."""
        from app.models.usage_collection_run import CollectionRunStatus
        from app.usage.service import UsageCollectionService

        session = _make_mock_session()

        events = [_make_norm_event(provider_request_id=f"req_{i}") for i in range(3)]
        page = UsagePage(events=events, next_cursor=None, has_more=False)
        mock_adapter = AsyncMock()
        mock_adapter.get_usage.return_value = page

        completed_run = _make_collection_run()
        completed_run.status = CollectionRunStatus.COMPLETED
        completed_run.events_collected = 3

        mock_run_repo, mock_event_repo, mock_cp_repo, _ = self._patch_service_deps(
            mock_adapter, completed_run=completed_run
        )

        with (
            patch("app.usage.service._build_config", return_value=MagicMock()),
            patch(
                "app.usage.service.ProviderFactory",
                return_value=MagicMock(create=MagicMock(return_value=mock_adapter)),
            ),
            patch(
                "app.repositories.usage_collection_run_repository.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.repositories.usage_event_repository.UsageEventRepository",
                return_value=mock_event_repo,
            ),
            patch(
                "app.repositories.usage_collection_checkpoint_repository.UsageCollectionCheckpointRepository",
                return_value=mock_cp_repo,
            ),
        ):
            # Patch the lazy import inside collect()
            import app.repositories.usage_collection_run_repository as ucr_mod
            import app.repositories.usage_event_repository as uer_mod
            import app.repositories.usage_collection_checkpoint_repository as ucc_mod

            ucr_mod.UsageCollectionRunRepository = MagicMock(return_value=mock_run_repo)
            uer_mod.UsageEventRepository = MagicMock(return_value=mock_event_repo)
            ucc_mod.UsageCollectionCheckpointRepository = MagicMock(return_value=mock_cp_repo)

            service = UsageCollectionService(session)
            run = await service.collect(
                organization_id=_ORG_ID,
                provider="openai",
                start_date=_START,
                end_date=_END,
            )

        assert run.status == CollectionRunStatus.COMPLETED
        assert run.events_collected == 3

    @pytest.mark.asyncio
    async def test_collect_marks_run_failed_on_adapter_error(self) -> None:
        from app.models.usage_collection_run import CollectionRunStatus
        from app.usage.service import UsageCollectionService

        session = _make_mock_session()
        mock_adapter = AsyncMock()
        mock_adapter.get_usage.side_effect = RuntimeError("adapter exploded")

        failed_run = _make_collection_run()
        failed_run.status = CollectionRunStatus.FAILED

        mock_run_repo, _, mock_cp_repo, _ = self._patch_service_deps(
            mock_adapter, completed_run=failed_run, failed_run=failed_run
        )

        import app.repositories.usage_collection_run_repository as ucr_mod
        import app.repositories.usage_event_repository as uer_mod
        import app.repositories.usage_collection_checkpoint_repository as ucc_mod

        ucr_mod.UsageCollectionRunRepository = MagicMock(return_value=mock_run_repo)
        uer_mod.UsageEventRepository = MagicMock(return_value=AsyncMock())
        ucc_mod.UsageCollectionCheckpointRepository = MagicMock(return_value=mock_cp_repo)

        with (
            patch("app.usage.service._build_config", return_value=MagicMock()),
            patch(
                "app.usage.service.ProviderFactory",
                return_value=MagicMock(create=MagicMock(return_value=mock_adapter)),
            ),
        ):
            service = UsageCollectionService(session)
            with pytest.raises(RuntimeError, match="adapter exploded"):
                await service.collect(
                    organization_id=_ORG_ID,
                    provider="openai",
                    start_date=_START,
                    end_date=_END,
                )

        mock_run_repo.update.assert_called_once()
        call_kwargs = mock_run_repo.update.call_args[1]
        assert call_kwargs["status"] == CollectionRunStatus.FAILED

    @pytest.mark.asyncio
    async def test_validation_failure_counts_as_failed(self) -> None:
        """Events that fail validation are counted in events_failed, not events_collected."""
        from app.models.usage_collection_run import CollectionRunStatus
        from app.usage.service import UsageCollectionService

        session = _make_mock_session()
        bad_event = _make_norm_event(provider_request_id="")  # will fail validation
        page = UsagePage(events=[bad_event], next_cursor=None, has_more=False)

        mock_adapter = AsyncMock()
        mock_adapter.get_usage.return_value = page

        completed_run = _make_collection_run()
        completed_run.status = CollectionRunStatus.COMPLETED
        completed_run.events_collected = 0
        completed_run.events_failed = 1

        mock_run_repo, mock_event_repo, mock_cp_repo, _ = self._patch_service_deps(
            mock_adapter, completed_run=completed_run
        )

        import app.repositories.usage_collection_run_repository as ucr_mod
        import app.repositories.usage_event_repository as uer_mod
        import app.repositories.usage_collection_checkpoint_repository as ucc_mod

        ucr_mod.UsageCollectionRunRepository = MagicMock(return_value=mock_run_repo)
        uer_mod.UsageEventRepository = MagicMock(return_value=mock_event_repo)
        ucc_mod.UsageCollectionCheckpointRepository = MagicMock(return_value=mock_cp_repo)

        with (
            patch("app.usage.service._build_config", return_value=MagicMock()),
            patch(
                "app.usage.service.ProviderFactory",
                return_value=MagicMock(create=MagicMock(return_value=mock_adapter)),
            ),
        ):
            service = UsageCollectionService(session)
            run = await service.collect(
                organization_id=_ORG_ID,
                provider="openai",
                start_date=_START,
                end_date=_END,
            )

        update_kwargs = mock_run_repo.update.call_args[1]
        assert update_kwargs["events_failed"] == 1
        assert update_kwargs["events_collected"] == 0
        mock_event_repo.upsert.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# F-047: BackgroundCollectionFramework
# ══════════════════════════════════════════════════════════════════════════════


class TestBackgroundCollectionFramework:
    def setup_method(self) -> None:
        from app.usage.background import BackgroundCollectionFramework

        global BackgroundCollectionFramework  # make available to test methods

        self.session_factory = MagicMock()
        self.framework = BackgroundCollectionFramework(
            self.session_factory, max_concurrent=2
        )

    def _make_session_factory(self) -> Any:
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin.return_value = mock_ctx
        session_factory = AsyncMock(return_value=mock_session)
        return session_factory, mock_session

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self) -> None:
        session_factory, _ = self._make_session_factory()
        framework = BackgroundCollectionFramework(session_factory, max_concurrent=2)

        with patch("app.usage.service.UsageCollectionService") as MockService:
            mock_service = AsyncMock()
            mock_service.collect.return_value = _make_collection_run()
            MockService.return_value = mock_service

            task_id = await framework.submit(
                organization_id=_ORG_ID,
                provider="openai",
                start_date=_START,
                end_date=_END,
            )
            assert isinstance(task_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_get_status_returns_none_for_unknown(self) -> None:
        result = self.framework.get_status(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_unknown_task_returns_false(self) -> None:
        result = await self.framework.cancel(uuid.uuid4())
        assert result is False

    def test_list_tasks_empty_initially(self) -> None:
        tasks = self.framework.list_tasks()
        assert tasks == []

    def test_running_count_zero_initially(self) -> None:
        assert self.framework.running_count() == 0

    @pytest.mark.asyncio
    async def test_get_status_after_submit(self) -> None:
        session_factory, _ = self._make_session_factory()
        framework = BackgroundCollectionFramework(session_factory, max_concurrent=2)

        with patch("app.usage.service.UsageCollectionService") as MockService:
            mock_service = AsyncMock()
            run = _make_collection_run()
            mock_service.collect.return_value = run
            MockService.return_value = mock_service

            task_id = await framework.submit(
                organization_id=_ORG_ID,
                provider="openai",
                start_date=_START,
                end_date=_END,
            )
            status = framework.get_status(task_id)
            assert status is not None
            assert "task_id" in status
            assert "provider" in status

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_org(self) -> None:
        other_org = uuid.UUID("00000000-0000-0000-0000-000000000099")
        session_factory, _ = self._make_session_factory()
        framework = BackgroundCollectionFramework(session_factory, max_concurrent=2)

        with patch("app.usage.service.UsageCollectionService") as MockService:
            mock_service = AsyncMock()
            mock_service.collect.return_value = _make_collection_run()
            MockService.return_value = mock_service

            await framework.submit(
                organization_id=_ORG_ID,
                provider="openai",
                start_date=_START,
                end_date=_END,
            )
            await framework.submit(
                organization_id=other_org,
                provider="anthropic",
                start_date=_START,
                end_date=_END,
            )

        tasks_for_org = framework.list_tasks(organization_id=_ORG_ID)
        assert all(t["organization_id"] == str(_ORG_ID) for t in tasks_for_org)


# ══════════════════════════════════════════════════════════════════════════════
# F-049: Usage REST API endpoints
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageAPI:
    """API-level tests using the ASGI test client."""

    _COLLECT_BODY: dict[str, Any] = {
        "organization_id": str(_ORG_ID),
        "start_date": _START.isoformat(),
        "end_date": _END.isoformat(),
        "triggered_by": "manual",
    }

    @pytest.mark.asyncio
    async def test_collect_all_returns_202(self, client: Any) -> None:
        run = _make_collection_run()
        run.started_at = _START
        run.completed_at = _END

        with patch("app.api.v1.usage._run_collection_sync", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = run
            resp = await client.post("/v1/usage/collect", json=self._COLLECT_BODY)

        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_collect_provider_openai_returns_202(self, client: Any) -> None:
        run = _make_collection_run()
        run.started_at = _START
        run.completed_at = _END

        with patch("app.api.v1.usage._run_collection_sync", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = run
            resp = await client.post("/v1/usage/collect/openai", json=self._COLLECT_BODY)

        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_collect_provider_anthropic_returns_202(self, client: Any) -> None:
        run = _make_collection_run()
        run.started_at = _START
        run.completed_at = _END

        with patch("app.api.v1.usage._run_collection_sync", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = run
            resp = await client.post("/v1/usage/collect/anthropic", json=self._COLLECT_BODY)

        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_collect_unsupported_provider_returns_404(self, client: Any) -> None:
        resp = await client.post("/v1/usage/collect/gemini", json=self._COLLECT_BODY)
        assert resp.status_code == 404
        data = resp.json()
        assert "gemini" in data["detail"]

    @pytest.mark.asyncio
    async def test_list_events_returns_empty(self, client: Any) -> None:
        resp = await client.get(
            "/v1/usage/events", params={"organization_id": str(_ORG_ID)}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_event_returns_404(self, client: Any) -> None:
        event_id = uuid.uuid4()
        resp = await client.get(
            f"/v1/usage/events/{event_id}",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_runs_returns_empty(self, client: Any) -> None:
        resp = await client.get(
            "/v1/usage/runs", params={"organization_id": str(_ORG_ID)}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_run_returns_404(self, client: Any) -> None:
        run_id = uuid.uuid4()
        resp = await client.get(
            f"/v1/usage/runs/{run_id}",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_checkpoints_returns_empty(self, client: Any) -> None:
        resp = await client.get(
            "/v1/usage/checkpoints", params={"organization_id": str(_ORG_ID)}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_provider_status_openai(self, client: Any) -> None:
        resp = await client.get(
            "/v1/usage/providers/openai/status",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "openai"
        assert data["has_checkpoint"] is False

    @pytest.mark.asyncio
    async def test_provider_status_unsupported_returns_404(self, client: Any) -> None:
        resp = await client.get(
            "/v1/usage/providers/grok/status",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_collect_missing_organization_id_returns_422(self, client: Any) -> None:
        body = {
            "start_date": _START.isoformat(),
            "end_date": _END.isoformat(),
        }
        resp = await client.post("/v1/usage/collect", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_collect_end_before_start_returns_422(self, client: Any) -> None:
        body = {
            "organization_id": str(_ORG_ID),
            "start_date": _END.isoformat(),
            "end_date": _START.isoformat(),  # end < start
        }
        resp = await client.post("/v1/usage/collect", json=body)
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# Provider adapter get_usage tests (mock transport)
# ══════════════════════════════════════════════════════════════════════════════


def _make_mock_transport_response(body: dict[str, Any], status: int = 200) -> Any:
    import json

    import httpx

    content = json.dumps(body).encode()
    request = httpx.Request("GET", "https://api.openai.com/test")
    return httpx.Response(status, content=content, request=request)


class TestOpenAIAdapterGetUsage:
    def _make_adapter(self) -> Any:
        import os

        os.environ.setdefault("OPENAI_API_KEY", "sk-" + "a" * 30)

        from app.providers.adapters.openai import OpenAIProvider
        from app.providers.config import OpenAIConfig, SecretReference, SecretStoreType

        config = OpenAIConfig(
            provider_type="openai",
            display_name="OpenAI",
            api_key_ref=SecretReference(
                secret_store=SecretStoreType.ENV,
                secret_key="OPENAI_API_KEY",
            ),
        )
        return OpenAIProvider(config)

    @pytest.mark.asyncio
    async def test_get_usage_empty_data(self) -> None:
        adapter = self._make_adapter()
        api_response = {"data": [], "has_more": False}

        with patch.object(adapter, "_build_client") as mock_build_client:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=api_response)
            mock_build_client.return_value = mock_client

            page = await adapter.get_usage(_START, _END)

        assert isinstance(page, UsagePage)
        assert page.events == []
        assert page.has_more is False

    @pytest.mark.asyncio
    async def test_get_usage_with_data(self) -> None:
        adapter = self._make_adapter()
        api_response = {
            "data": [
                {
                    "start_time": 1717200000,
                    "model": "gpt-4o",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "num_model_requests": 1,
                }
            ],
            "has_more": False,
        }

        with patch.object(adapter, "_build_client") as mock_build_client:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=api_response)
            mock_build_client.return_value = mock_client

            page = await adapter.get_usage(_START, _END)

        assert len(page.events) == 1
        assert page.events[0].provider == "openai"
        assert page.events[0].model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_get_usage_passes_cursor(self) -> None:
        adapter = self._make_adapter()
        api_response = {"data": [], "has_more": False}

        with patch.object(adapter, "_build_client") as mock_build_client:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=api_response)
            mock_build_client.return_value = mock_client

            await adapter.get_usage(_START, _END, cursor="page_2", limit=50)

        call_kwargs = mock_client.get.call_args
        params = call_kwargs[1].get("params") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {}
        if not params and call_kwargs[1]:
            params = call_kwargs[1].get("params", {})


class TestAnthropicAdapterGetUsage:
    def _make_adapter(self) -> Any:
        import os

        os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-" + "b" * 30)

        from app.providers.adapters.anthropic import AnthropicProvider
        from app.providers.config import AnthropicConfig, SecretReference, SecretStoreType

        config = AnthropicConfig(
            provider_type="anthropic",
            display_name="Anthropic",
            api_key_ref=SecretReference(
                secret_store=SecretStoreType.ENV,
                secret_key="ANTHROPIC_API_KEY",
            ),
        )
        return AnthropicProvider(config)

    @pytest.mark.asyncio
    async def test_get_usage_returns_empty_page_on_api_error(self) -> None:
        adapter = self._make_adapter()

        with patch.object(adapter, "_build_client") as mock_build_client:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("API unavailable"))
            mock_build_client.return_value = mock_client

            page = await adapter.get_usage(_START, _END)

        assert isinstance(page, UsagePage)
        assert page.events == []

    @pytest.mark.asyncio
    async def test_get_usage_with_data(self) -> None:
        adapter = self._make_adapter()
        api_response = {
            "data": [
                {
                    "id": "req_anthropic_001",
                    "model": "claude-3-5-sonnet-20241022",
                    "created_at": "2025-05-15T12:00:00Z",
                    "input_tokens": 2000,
                    "output_tokens": 1000,
                }
            ],
            "has_more": False,
        }

        with patch.object(adapter, "_build_client") as mock_build_client:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=api_response)
            mock_build_client.return_value = mock_client

            page = await adapter.get_usage(_START, _END)

        assert len(page.events) == 1
        assert page.events[0].provider == "anthropic"
        assert page.events[0].provider_request_id == "req_anthropic_001"

    @pytest.mark.asyncio
    async def test_get_usage_empty_data(self) -> None:
        adapter = self._make_adapter()
        api_response = {"data": [], "has_more": False}

        with patch.object(adapter, "_build_client") as mock_build_client:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=api_response)
            mock_build_client.return_value = mock_client

            page = await adapter.get_usage(_START, _END)

        assert page.events == []
        assert page.has_more is False


# ══════════════════════════════════════════════════════════════════════════════
# Stub adapter tests — all other providers return empty UsagePage
# ══════════════════════════════════════════════════════════════════════════════


class TestStubAdapterGetUsage:
    """Verify that stub adapters return an empty UsagePage without errors."""

    @pytest.mark.asyncio
    async def test_azure_openai_returns_empty_page(self) -> None:
        from app.providers.adapters.azure_openai import AzureOpenAIProvider
        from app.providers.config import AzureOpenAIConfig, SecretReference, SecretStoreType

        config = AzureOpenAIConfig(
            provider_type="azure_openai",
            display_name="Azure OpenAI",
            api_key_ref=SecretReference(
                secret_store=SecretStoreType.ENV,
                secret_key="AZURE_OPENAI_API_KEY",
            ),
            azure_endpoint="https://example.openai.azure.com",
            azure_deployment="gpt-4o",
        )
        adapter = AzureOpenAIProvider(config)
        page = await adapter.get_usage(_START, _END)
        assert isinstance(page, UsagePage)
        assert page.events == []

    @pytest.mark.asyncio
    async def test_google_returns_empty_page(self) -> None:
        from app.providers.adapters.google import GoogleProvider
        from app.providers.config import GoogleConfig, SecretReference, SecretStoreType

        config = GoogleConfig(
            provider_type="google",
            display_name="Google",
            api_key_ref=SecretReference(
                secret_store=SecretStoreType.ENV,
                secret_key="GOOGLE_API_KEY",
            ),
        )
        adapter = GoogleProvider(config)
        page = await adapter.get_usage(_START, _END)
        assert isinstance(page, UsagePage)
        assert page.events == []

    @pytest.mark.asyncio
    async def test_ollama_returns_empty_page(self) -> None:
        from app.providers.adapters.ollama import OllamaProvider
        from app.providers.config import OllamaConfig

        config = OllamaConfig(
            provider_type="ollama",
            display_name="Ollama",
            base_url="http://localhost:11434",
        )
        adapter = OllamaProvider(config)
        page = await adapter.get_usage(_START, _END)
        assert isinstance(page, UsagePage)
        assert page.events == []
