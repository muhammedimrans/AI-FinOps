"""
Generic async repository base for all AI FinOps entities.

Design:
  - BaseRepository[T] is parametrised on a concrete BaseModel subclass.
  - All queries filter `deleted_at IS NULL` by default (soft-delete DP-7).
  - Cursor-based pagination is keyed on (created_at, id) per §API-7.
  - Cursors are opaque base64-encoded JSON strings safe to expose in APIs.
  - No session management here — callers pass an AsyncSession and manage
    commit/rollback via get_session() or managed_transaction().
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import BaseModel

T = TypeVar("T", bound=BaseModel)


# ─── Pagination ───────────────────────────────────────────────────────────────


class CursorPage(Generic[T]):
    """
    A page of results for cursor-based pagination (§API-7).

    Attributes:
        items       — the records on this page
        next_cursor — opaque token to fetch the next page; None if last page
        has_more    — True when there are more records beyond this page
    """

    __slots__ = ("items", "next_cursor", "has_more")

    def __init__(
        self,
        items: list[T],
        *,
        next_cursor: str | None,
        has_more: bool,
    ) -> None:
        self.items = items
        self.next_cursor = next_cursor
        self.has_more = has_more

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
        }


def _encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    """Encode (created_at, id) into an opaque URL-safe base64 cursor token."""
    payload = json.dumps(
        {"ca": created_at.isoformat(), "id": str(record_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """
    Decode an opaque cursor token back to (created_at, id).
    Raises ValueError for any malformed input.
    """
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(payload)
        created_at = datetime.fromisoformat(data["ca"])
        record_id = uuid.UUID(data["id"])
        return created_at, record_id
    except Exception as exc:
        raise ValueError(f"Invalid cursor token: {exc}") from exc


# ─── Repository ───────────────────────────────────────────────────────────────


class BaseRepository(Generic[T]):
    """
    Generic async repository providing CRUD, cursor-paginated list, and
    soft-delete operations.

    Usage::

        class OrganizationRepository(BaseRepository[Organization]):
            model = Organization

        repo = OrganizationRepository(session)
        org  = await repo.get(some_uuid)
        page = await repo.list_page(limit=20)
    """

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _active_query(self) -> Select[tuple[T]]:
        """Base SELECT that excludes soft-deleted records."""
        # type: ignore[attr-defined] — Mypy cannot resolve .deleted_at through
        # Generic[T] even though T is bound to BaseModel (which has the column).
        # SQLAlchemy's Mypy plugin handles ORM column access at the concrete
        # class level, not through generics. The ignore is correct; do not remove.
        return select(self.model).where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def get(self, record_id: uuid.UUID) -> T | None:
        """Return the active record with the given primary key, or None."""
        stmt = self._active_query().where(self.model.id == record_id)  # type: ignore[attr-defined]
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_raise(self, record_id: uuid.UUID) -> T:
        """Return the active record or raise KeyError."""
        record = await self.get(record_id)
        if record is None:
            raise KeyError(
                f"{self.model.__name__} {record_id} not found or has been deleted"
            )
        return record

    async def create(self, instance: T) -> T:
        """Persist a new instance. Does NOT commit — caller manages transaction."""
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def update(self, instance: T, **kwargs: Any) -> T:
        """
        Apply keyword updates to an existing instance and flush.

        Raises AttributeError for unknown keys so silent data loss is
        impossible — if a key isn't a model attribute, it would be set on
        the Python instance but never persisted (SQLAlchemy ignores unknown
        instance attributes on flush). The guard prevents that foot-gun.
        """
        for key, value in kwargs.items():
            if not hasattr(instance, key):
                raise AttributeError(
                    f"{type(instance).__name__} has no attribute {key!r}. "
                    f"Check the column name and try again."
                )
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def soft_delete(
        self,
        instance: T,
        deleted_by: uuid.UUID | None = None,
    ) -> T:
        """
        Mark the record as deleted. Uses the mixin's soft_delete() method
        which sets deleted_at and deleted_by atomically.
        """
        instance.soft_delete(deleted_by=deleted_by)  # type: ignore[attr-defined]
        await self._session.flush()
        return instance

    async def hard_delete(self, instance: T) -> None:
        """
        Physically remove the record. Admin / test contexts only.
        Prefer soft_delete() for normal application flows.
        """
        await self._session.delete(instance)
        await self._session.flush()

    # ── List / Pagination ─────────────────────────────────────────────────────

    async def list_page(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
        extra_filters: Any = None,
    ) -> CursorPage[T]:
        """
        Return a cursor-paginated page of active records ordered by (created_at, id).

        Args:
            limit        — page size; capped at 100 internally
            cursor       — opaque token from a previous response's next_cursor
            order        — "asc" (oldest first) or "desc" (newest first)
            extra_filters — additional SQLAlchemy WHERE clause(s) to AND in
        """
        limit = min(limit, 100)
        is_asc = order.lower() != "desc"

        stmt = self._active_query()

        if extra_filters is not None:
            stmt = stmt.where(extra_filters)

        if cursor is not None:
            pivot_created_at, pivot_id = _decode_cursor(cursor)
            if is_asc:
                stmt = stmt.where(
                    or_(
                        self.model.created_at > pivot_created_at,  # type: ignore[attr-defined]
                        and_(
                            self.model.created_at == pivot_created_at,  # type: ignore[attr-defined]
                            self.model.id > pivot_id,  # type: ignore[attr-defined]
                        ),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        self.model.created_at < pivot_created_at,  # type: ignore[attr-defined]
                        and_(
                            self.model.created_at == pivot_created_at,  # type: ignore[attr-defined]
                            self.model.id < pivot_id,  # type: ignore[attr-defined]
                        ),
                    )
                )

        order_col_ts = self.model.created_at  # type: ignore[attr-defined]
        order_col_id = self.model.id  # type: ignore[attr-defined]
        if is_asc:
            stmt = stmt.order_by(asc(order_col_ts), asc(order_col_id))
        else:
            stmt = stmt.order_by(desc(order_col_ts), desc(order_col_id))

        stmt = stmt.limit(limit + 1)

        result = await self._session.execute(stmt)
        rows: list[T] = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)  # type: ignore[attr-defined]

        return CursorPage(items=rows, next_cursor=next_cursor, has_more=has_more)

    async def count(self, extra_filters: Any = None) -> int:
        """Return the count of active (non-deleted) records."""
        stmt = select(func.count()).select_from(self.model).where(
            self.model.deleted_at.is_(None)  # type: ignore[attr-defined]
        )
        if extra_filters is not None:
            stmt = stmt.where(extra_filters)
        result = await self._session.execute(stmt)
        return result.scalar_one()
