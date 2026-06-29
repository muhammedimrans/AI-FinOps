"""
Tests for EP-04 - Users & Identity Foundation.

Covers (without a live database):
  - User model attributes, defaults, constraints, and soft-delete
  - Membership.user_id FK column and relationship
  - UserRepository method signatures (mock session)
  - validate_user_email: valid paths and all error branches
  - validate_display_name: valid paths and all error branches
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.validators import validate_display_name, validate_user_email
from app.db.mixins import uuid7
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.repositories.user_repository import UserRepository

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(
    *,
    email: str = "alice@example.com",
    display_name: str = "Alice",
    is_active: bool = True,
) -> User:
    obj = User()
    obj.id = uuid7()
    obj.email = email
    obj.display_name = display_name
    obj.is_active = is_active
    return obj


def _make_mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# ── F-013: User model ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestUserModel:
    def test_tablename(self) -> None:
        assert User.__tablename__ == "users"

    def test_external_id_prefix(self) -> None:
        user = _make_user()
        assert user.external_id.startswith("usr_")

    def test_external_id_contains_no_hyphens(self) -> None:
        user = _make_user()
        assert "-" not in user.external_id

    def test_default_is_active(self) -> None:
        user = _make_user()
        assert user.is_active is True

    def test_inactive_user(self) -> None:
        user = _make_user(is_active=False)
        assert user.is_active is False

    def test_avatar_url_defaults_to_none(self) -> None:
        user = _make_user()
        assert user.avatar_url is None

    def test_bio_defaults_to_none(self) -> None:
        user = _make_user()
        assert user.bio is None

    def test_soft_delete_sets_deleted_at(self) -> None:
        from datetime import UTC

        user = _make_user()
        assert user.deleted_at is None
        actor_id = uuid.uuid4()
        user.soft_delete(deleted_by=actor_id)
        assert user.deleted_at is not None
        assert user.deleted_by == actor_id
        assert user.deleted_at.tzinfo == UTC
        assert user.is_deleted is True

    def test_repr_contains_class_name(self) -> None:
        user = _make_user()
        assert "User" in repr(user)

    def test_unique_email_constraint_name(self) -> None:
        constraint_names = {
            c.name for c in User.__table_args__ if hasattr(c, "name") and c.name is not None
        }
        assert "uq_users_email" in constraint_names

    def test_cursor_index_created(self) -> None:
        index_names = {
            c.name for c in User.__table_args__ if hasattr(c, "name") and c.name is not None
        }
        assert "ix_users_cursor" in index_names

    def test_deleted_index_created(self) -> None:
        index_names = {
            c.name for c in User.__table_args__ if hasattr(c, "name") and c.name is not None
        }
        assert "ix_users_deleted" in index_names


# ── F-014: Membership refactor — user_id FK ───────────────────────────────────


@pytest.mark.unit
class TestMembershipUserIdField:
    def test_user_id_column_exists(self) -> None:
        mem = Membership()
        assert hasattr(mem, "user_id")

    def test_user_id_defaults_to_none(self) -> None:
        mem = Membership()
        mem.id = uuid7()
        mem.organization_id = uuid7()
        mem.user_email = "bob@example.com"
        mem.role = MembershipRole.MEMBER
        assert mem.user_id is None

    def test_user_id_can_be_set(self) -> None:
        uid = uuid.uuid4()
        mem = Membership()
        mem.user_id = uid
        assert mem.user_id == uid

    def test_membership_user_id_index_created(self) -> None:
        index_names = {
            c.name for c in Membership.__table_args__ if hasattr(c, "name") and c.name is not None
        }
        assert "ix_memberships_user_id" in index_names


# ── F-015: UserRepository ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestUserRepository:
    def test_model_attribute(self) -> None:
        assert UserRepository.model is User

    async def test_get_by_email_calls_execute(self) -> None:
        session = _make_mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        repo = UserRepository(session)
        result = await repo.get_by_email("alice@example.com")
        assert result is None
        session.execute.assert_called_once()

    async def test_email_exists_returns_bool(self) -> None:
        session = _make_mock_session()
        session.execute.return_value.scalar_one = MagicMock(return_value=True)
        repo = UserRepository(session)
        exists = await repo.email_exists("alice@example.com")
        assert exists is True

    async def test_email_exists_with_exclude_id(self) -> None:
        session = _make_mock_session()
        session.execute.return_value.scalar_one = MagicMock(return_value=False)
        repo = UserRepository(session)
        exists = await repo.email_exists("alice@example.com", exclude_id=uuid.uuid4())
        assert exists is False
        session.execute.assert_called_once()

    async def test_list_active_delegates_to_list_page(self) -> None:
        session = _make_mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock
        repo = UserRepository(session)
        page = await repo.list_active(limit=10)
        assert page.items == []
        assert page.has_more is False

    async def test_count_active_returns_int(self) -> None:
        session = _make_mock_session()
        session.execute.return_value.scalar_one = MagicMock(return_value=3)
        repo = UserRepository(session)
        count = await repo.count_active()
        assert count == 3

    async def test_create_adds_and_flushes(self) -> None:
        session = _make_mock_session()
        session.refresh = AsyncMock()
        repo = UserRepository(session)
        user = _make_user()
        await repo.create(user)
        session.add.assert_called_once_with(user)
        session.flush.assert_called_once()

    async def test_get_or_raise_raises_key_error_for_missing(self) -> None:
        session = _make_mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        repo = UserRepository(session)
        with pytest.raises(KeyError, match="User"):
            await repo.get_or_raise(uuid.uuid4())


# ── F-016: User validation ────────────────────────────────────────────────────


@pytest.mark.unit
class TestValidateUserEmail:
    def test_valid_email_passes(self) -> None:
        validate_user_email("alice@example.com")  # must not raise

    def test_valid_email_with_plus(self) -> None:
        validate_user_email("alice+tag@example.org")

    def test_valid_email_with_subdomain(self) -> None:
        validate_user_email("user@mail.example.co.uk")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_user_email("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_user_email("   ")

    def test_too_long_raises(self) -> None:
        long_email = "a" * 310 + "@example.com"
        with pytest.raises(ValueError, match="320"):
            validate_user_email(long_email)

    def test_missing_at_raises(self) -> None:
        with pytest.raises(ValueError, match="valid email"):
            validate_user_email("not-an-email")

    def test_missing_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="valid email"):
            validate_user_email("user@")

    def test_missing_local_part_raises(self) -> None:
        with pytest.raises(ValueError, match="valid email"):
            validate_user_email("@example.com")

    def test_domain_without_tld_raises(self) -> None:
        with pytest.raises(ValueError, match="valid email"):
            validate_user_email("user@localhost")


@pytest.mark.unit
class TestValidateDisplayName:
    def test_valid_name_passes(self) -> None:
        validate_display_name("Alice")  # must not raise

    def test_single_char_passes(self) -> None:
        validate_display_name("A")

    def test_max_length_passes(self) -> None:
        validate_display_name("A" * 255)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_display_name("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_display_name("   ")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="255"):
            validate_display_name("A" * 256)
