"""
Tests for F-006 – Base ORM Classes.

Covers:
  - uuid7() uniqueness, version, and variant bits
  - UUIDMixin: external_id prefix, property
  - TimestampMixin: column presence
  - SoftDeleteMixin: is_deleted property
  - BaseModel: __abstract__, __repr__
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.base import (
    BaseModel,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    uuid7,
)


# ─── uuid7() ─────────────────────────────────────────────────────────────────


class TestUuid7:
    def test_returns_uuid(self) -> None:
        result = uuid7()
        assert isinstance(result, uuid.UUID)

    def test_version_is_7(self) -> None:
        result = uuid7()
        # bits 48-51 of the 128-bit int encode the version
        version = (result.int >> 76) & 0xF
        assert version == 7

    def test_variant_is_rfc4122(self) -> None:
        result = uuid7()
        # RFC 4122 variant: top two bits of octet 8 are 0b10
        variant_bits = (result.int >> 62) & 0b11
        assert variant_bits == 0b10

    def test_unique(self) -> None:
        ids = [uuid7() for _ in range(1000)]
        assert len(set(ids)) == 1000

    def test_monotonically_increasing(self) -> None:
        """Sequential UUIDs should have non-decreasing timestamp prefixes."""
        ids = [uuid7() for _ in range(100)]
        timestamps = [(u.int >> 80) for u in ids]
        assert timestamps == sorted(timestamps)


# ─── Mixins via concrete test model ──────────────────────────────────────────


class _FakeModel(BaseModel):
    """Minimal concrete model for mixin testing — never mapped to a real table."""

    __tablename__ = "fake_models"
    __abstract__ = False
    _external_id_prefix = "fake"

    # Suppress index auto-creation for unit tests (no DDL needed)
    __table_args__ = ()  # type: ignore[assignment]


def _make_fake(
    id: uuid.UUID | None = None,
    deleted_at: datetime | None = None,
) -> _FakeModel:
    """
    Create a transient _FakeModel instance (no DB session needed).
    Calling the class constructor properly initialises _sa_instance_state
    so SQLAlchemy's column descriptors work correctly without a live DB.
    """
    obj = _FakeModel()
    obj.id = id or uuid7()  # ORM descriptor works once state is initialised
    obj.deleted_at = deleted_at
    return obj


class TestUUIDMixin:
    def test_external_id_format(self) -> None:
        fixed_id = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
        obj = _make_fake(id=fixed_id)
        assert obj.external_id == "fake_0123456789abcdef0123456789abcdef"

    def test_external_id_prefix(self) -> None:
        obj = _make_fake()
        assert obj.external_id.startswith("fake_")

    def test_external_id_no_hyphens(self) -> None:
        obj = _make_fake()
        assert "-" not in obj.external_id


class TestTimestampMixin:
    def test_has_created_at_column(self) -> None:
        assert hasattr(TimestampMixin, "created_at")

    def test_has_updated_at_column(self) -> None:
        assert hasattr(TimestampMixin, "updated_at")


class TestSoftDeleteMixin:
    def test_is_deleted_false_when_no_deleted_at(self) -> None:
        obj = _make_fake(deleted_at=None)
        assert obj.is_deleted is False

    def test_is_deleted_true_when_deleted_at_set(self) -> None:
        obj = _make_fake(deleted_at=datetime.now(tz=timezone.utc))
        assert obj.is_deleted is True

    def test_has_deleted_by_column(self) -> None:
        assert hasattr(SoftDeleteMixin, "deleted_by")

    def test_soft_delete_method_sets_deleted_at(self) -> None:
        obj = _make_fake()
        assert obj.deleted_at is None
        obj.soft_delete()
        assert obj.deleted_at is not None
        assert obj.is_deleted is True

    def test_soft_delete_method_records_actor(self) -> None:
        obj = _make_fake()
        actor = uuid.uuid4()
        obj.soft_delete(deleted_by=actor)
        assert obj.deleted_by == actor


class TestBaseModel:
    def test_abstract_flag(self) -> None:
        assert BaseModel.__abstract__ is True

    def test_repr_contains_class_name(self) -> None:
        obj = _make_fake()
        r = repr(obj)
        assert "_FakeModel" in r

    def test_repr_contains_external_id(self) -> None:
        obj = _make_fake()
        r = repr(obj)
        assert "fake_" in r
