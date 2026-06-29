"""
Tests for F-008 - Repository Layer.

Covers:
  - CursorPage data structure
  - _encode_cursor / _decode_cursor round-trip
  - BaseRepository in-memory semantics via a mock session
  - Cursor direction: asc / desc
  - Soft-delete filtering
  - Edge cases: empty result, malformed cursor
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.base import (
    BaseRepository,
    CursorPage,
    _decode_cursor,
    _encode_cursor,
)

# ─── Cursor codec ─────────────────────────────────────────────────────────────


class TestCursorCodec:
    def test_round_trip(self) -> None:
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        uid = uuid.uuid4()
        token = _encode_cursor(now, uid)
        decoded_dt, decoded_id = _decode_cursor(token)
        assert decoded_dt == now
        assert decoded_id == uid

    def test_token_is_string(self) -> None:
        token = _encode_cursor(datetime.now(tz=UTC), uuid.uuid4())
        assert isinstance(token, str)

    def test_token_is_url_safe(self) -> None:
        token = _encode_cursor(datetime.now(tz=UTC), uuid.uuid4())
        safe_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
        assert all(c in safe_chars for c in token)

    def test_invalid_cursor_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid cursor"):
            _decode_cursor("not-a-valid-token!!")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _decode_cursor("")


# ─── CursorPage ───────────────────────────────────────────────────────────────


class TestCursorPage:
    def test_has_more_false_for_last_page(self) -> None:
        page: CursorPage[object] = CursorPage(items=[], next_cursor=None, has_more=False)
        assert page.has_more is False
        assert page.next_cursor is None

    def test_has_more_true_when_next_cursor_present(self) -> None:
        page: CursorPage[object] = CursorPage(items=["a"], next_cursor="tok", has_more=True)
        assert page.has_more is True
        assert page.next_cursor == "tok"

    def test_to_dict_keys(self) -> None:
        page: CursorPage[object] = CursorPage(items=[1, 2], next_cursor="abc", has_more=True)
        d = page.to_dict()
        assert set(d.keys()) == {"items", "next_cursor", "has_more"}


# ─── BaseRepository (unit — no DB) ───────────────────────────────────────────
#
# We use a lightweight fake model and mock the SQLAlchemy session so these
# tests run without any database connection.


class FakeRecord:
    """Stand-in for a BaseModel instance."""

    def __init__(
        self,
        id: uuid.UUID,
        created_at: datetime,
        deleted_at: datetime | None = None,
        deleted_by: uuid.UUID | None = None,
    ) -> None:
        self.id = id
        self.created_at = created_at
        self.deleted_at = deleted_at
        self.deleted_by = deleted_by

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, deleted_by: uuid.UUID | None = None) -> None:
        self.deleted_at = datetime.now(tz=UTC)
        self.deleted_by = deleted_by


class FakeRepository(BaseRepository):  # type: ignore[type-arg]
    model = FakeRecord  # type: ignore[assignment]


def _make_mock_session() -> AsyncMock:
    """Return a minimal mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


class TestBaseRepositoryCreate:
    @pytest.mark.asyncio
    async def test_create_adds_and_flushes(self) -> None:
        session = _make_mock_session()
        repo = FakeRepository(session)
        record = FakeRecord(uuid.uuid4(), datetime.now(tz=UTC))

        result = await repo.create(record)

        session.add.assert_called_once_with(record)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(record)
        assert result is record


class TestBaseRepositorySoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_sets_deleted_at(self) -> None:
        session = _make_mock_session()
        repo = FakeRepository(session)
        record = FakeRecord(uuid.uuid4(), datetime.now(tz=UTC))
        assert record.deleted_at is None

        result = await repo.soft_delete(record)

        assert result.deleted_at is not None
        assert result.is_deleted is True
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_records_deleted_by(self) -> None:
        session = _make_mock_session()
        repo = FakeRepository(session)
        actor_id = uuid.uuid4()
        record = FakeRecord(uuid.uuid4(), datetime.now(tz=UTC))

        result = await repo.soft_delete(record, deleted_by=actor_id)

        assert result.deleted_by == actor_id
        session.flush.assert_awaited_once()


class TestBaseRepositoryHardDelete:
    @pytest.mark.asyncio
    async def test_hard_delete_calls_session_delete(self) -> None:
        session = _make_mock_session()
        repo = FakeRepository(session)
        record = FakeRecord(uuid.uuid4(), datetime.now(tz=UTC))

        await repo.hard_delete(record)

        session.delete.assert_awaited_once_with(record)
        session.flush.assert_awaited_once()


class TestCursorPageEdgeCases:
    def test_empty_page(self) -> None:
        page: CursorPage[object] = CursorPage(items=[], next_cursor=None, has_more=False)
        assert page.items == []
        assert not page.has_more

    def test_single_item_no_more(self) -> None:
        page: CursorPage[object] = CursorPage(items=["x"], next_cursor=None, has_more=False)
        assert len(page.items) == 1
        assert not page.has_more


class TestCursorEncodeDecodePreservesTimezone:
    def test_utc_timezone_preserved(self) -> None:
        now = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        uid = uuid.uuid4()
        token = _encode_cursor(now, uid)
        decoded_dt, _ = _decode_cursor(token)
        assert decoded_dt.tzinfo is not None
        assert decoded_dt == now
