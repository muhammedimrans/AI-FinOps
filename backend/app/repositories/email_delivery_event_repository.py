"""EmailDeliveryEventRepository — data access for Resend delivery webhooks (EP-25.3)."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_delivery_event import EmailDeliveryEvent
from app.repositories.base_repository import BaseRepository


class EmailDeliveryEventRepository(BaseRepository[EmailDeliveryEvent]):
    """Repository for the append-only email delivery-event log."""

    model = EmailDeliveryEvent

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_for_message(
        self, provider_message_id: str, *, limit: int = 50
    ) -> list[EmailDeliveryEvent]:
        """Every event recorded for one provider message, newest first —
        the "delivery status" of a single sent email as its full history,
        not a single derived field (see the model's own docstring)."""
        stmt = (
            self._active_query()
            .where(EmailDeliveryEvent.provider_message_id == provider_message_id)
            .order_by(desc(EmailDeliveryEvent.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, *, limit: int = 100) -> list[EmailDeliveryEvent]:
        """Most recent events across every recipient — used by the admin-
        facing "recent delivery failures" surface, if/when one is built."""
        stmt = self._active_query().order_by(desc(EmailDeliveryEvent.created_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_status_for_message(self, provider_message_id: str) -> str | None:
        """The most recent event_type recorded for a provider message, or
        ``None`` if no webhook has ever fired for it (e.g. Resend hasn't
        called back yet, or delivery-event webhooks aren't configured)."""
        stmt = (
            select(EmailDeliveryEvent.event_type)
            .where(
                EmailDeliveryEvent.provider_message_id == provider_message_id,
                EmailDeliveryEvent.deleted_at.is_(None),
            )
            .order_by(desc(EmailDeliveryEvent.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
