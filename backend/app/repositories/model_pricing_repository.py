"""ModelPricingRepository — F-051 (EP-09).

Provides pricing lookup methods for the PricingEngine including historical
date-based resolution.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_

from app.models.model_pricing import ModelPricing
from app.repositories.base_repository import BaseRepository


class ModelPricingRepository(BaseRepository[ModelPricing]):
    """Repository for ModelPricing records."""

    model = ModelPricing

    async def get_active_for_model(self, provider: str, model: str) -> ModelPricing | None:
        """Return the currently active pricing (effective_to IS NULL, is_active=True)."""
        stmt = (
            self._active_query()
            .where(
                and_(
                    ModelPricing.provider == provider,
                    ModelPricing.model == model,
                    ModelPricing.effective_to.is_(None),
                    ModelPricing.is_active.is_(True),
                )
            )
            .order_by(ModelPricing.effective_from.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_date(
        self, provider: str, model: str, usage_date: date
    ) -> ModelPricing | None:
        """Return pricing effective on the given date for historical cost calculation.

        Selects records where:
          effective_from <= usage_date
          AND (effective_to IS NULL OR effective_to >= usage_date)
        Orders by effective_from DESC to prefer the most recent version.
        """
        stmt = (
            self._active_query()
            .where(
                and_(
                    ModelPricing.provider == provider,
                    ModelPricing.model == model,
                    ModelPricing.is_active.is_(True),
                    ModelPricing.effective_from <= usage_date,
                    or_(
                        ModelPricing.effective_to.is_(None),
                        ModelPricing.effective_to >= usage_date,
                    ),
                )
            )
            .order_by(ModelPricing.effective_from.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_provider(self, provider: str) -> list[ModelPricing]:
        """All active (non-deleted) pricing records for a provider."""
        stmt = (
            self._active_query()
            .where(ModelPricing.provider == provider)
            .order_by(ModelPricing.model, ModelPricing.effective_from.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_model(self, provider: str, model: str) -> list[ModelPricing]:
        """All pricing versions for a (provider, model) pair, newest first."""
        stmt = (
            self._active_query()
            .where(
                and_(
                    ModelPricing.provider == provider,
                    ModelPricing.model == model,
                )
            )
            .order_by(ModelPricing.effective_from.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_version(self, provider: str, model: str, version: str) -> ModelPricing | None:
        """Get a specific pricing version by (provider, model, version) tuple."""
        stmt = self._active_query().where(
            and_(
                ModelPricing.provider == provider,
                ModelPricing.model == model,
                ModelPricing.version == version,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
