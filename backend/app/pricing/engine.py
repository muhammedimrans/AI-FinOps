"""PricingEngine — F-051 (EP-09).

Resolves applicable pricing version and calculates cost deterministically.
All arithmetic uses Decimal with ROUND_HALF_UP at 8 decimal places.
Never uses float for monetary values.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.models.model_pricing import ModelPricing
    from app.models.usage_event import UsageEvent
    from app.repositories.model_pricing_repository import ModelPricingRepository

log = structlog.get_logger(__name__)

CALCULATION_VERSION = "1.0"

# 8 decimal places for all computed cost values
_QUANT = Decimal("0.00000001")


class PricingNotFoundError(Exception):
    """No pricing configuration found for this provider/model/date."""


class PricingEngine:
    """
    Resolves applicable pricing version and calculates cost deterministically.

    All arithmetic uses Decimal with ROUND_HALF_UP at 8 decimal places.
    Never uses float. Currency is always stored; default is "USD".
    """

    def __init__(self, pricing_repo: ModelPricingRepository) -> None:
        self._repo = pricing_repo

    async def get_pricing_for_event(
        self,
        provider: str,
        model: str,
        usage_date: date,
    ) -> ModelPricing:
        """Resolve the applicable pricing for the given provider/model/date.

        Raises PricingNotFoundError if no pricing configuration is found.
        """
        pricing = await self._repo.get_for_date(provider, model, usage_date)
        if pricing is None:
            log.warning(
                "pricing_not_found",
                provider=provider,
                model=model,
                usage_date=str(usage_date),
            )
            raise PricingNotFoundError(
                f"No pricing configuration found for {provider}/{model} on {usage_date}"
            )
        log.debug(
            "pricing_resolved",
            provider=provider,
            model=model,
            usage_date=str(usage_date),
            pricing_id=str(pricing.id),
            version=pricing.version,
        )
        return pricing

    def calculate_cost(
        self,
        pricing: ModelPricing,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Compute costs from token counts using the given pricing record.

        Returns a dict with:
          prompt_cost       — Decimal, rounded to 8dp
          completion_cost   — Decimal, rounded to 8dp
          cached_cost       — Decimal | None, rounded to 8dp
          total_cost        — Decimal, rounded to 8dp
          currency          — str from pricing record
          model_pricing_id  — UUID of the pricing record used
          calculation_version — version string

        Never uses float. All values quantized to ROUND_HALF_UP 8dp.
        """
        prompt_cost = (Decimal(prompt_tokens) * pricing.prompt_token_price).quantize(
            _QUANT, rounding=ROUND_HALF_UP
        )
        completion_cost = (Decimal(completion_tokens) * pricing.completion_token_price).quantize(
            _QUANT, rounding=ROUND_HALF_UP
        )

        cached_cost = None
        if cached_tokens is not None and pricing.cached_token_price is not None:
            cached_cost = (Decimal(cached_tokens) * pricing.cached_token_price).quantize(
                _QUANT, rounding=ROUND_HALF_UP
            )

        total_cost = (prompt_cost + completion_cost + (cached_cost or Decimal(0))).quantize(
            _QUANT, rounding=ROUND_HALF_UP
        )

        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "cached_cost": cached_cost,
            "total_cost": total_cost,
            "currency": pricing.currency,
            "model_pricing_id": pricing.id,
            "calculation_version": CALCULATION_VERSION,
        }

    async def calculate_event_cost(
        self,
        usage_event: UsageEvent,
        usage_date: date,
    ) -> dict[str, Any]:
        """Convenience: resolve pricing + calculate cost from a UsageEvent.

        Raises PricingNotFoundError if no pricing is found for the event's
        provider/model on the given usage_date.
        """
        pricing = await self.get_pricing_for_event(
            usage_event.provider,
            usage_event.model,
            usage_date,
        )
        return self.calculate_cost(
            pricing,
            prompt_tokens=usage_event.prompt_tokens,
            completion_tokens=usage_event.completion_tokens,
            cached_tokens=usage_event.cached_tokens,
        )
