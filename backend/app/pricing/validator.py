"""PricingValidator — F-056 (EP-09).

Validates pricing configurations before persistence, ensuring:
- Required fields are non-empty
- Price values are non-negative
- Effective date ranges are valid
- No overlapping pricing versions exist for the same (provider, model)
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.models.model_pricing import ModelPricing
    from app.repositories.model_pricing_repository import ModelPricingRepository

log = structlog.get_logger(__name__)


class PricingValidationError(Exception):
    """Raised when a pricing configuration fails validation."""


class PricingValidator:
    """Validates pricing configurations before persistence."""

    def validate_new_pricing(self, pricing: ModelPricing) -> None:
        """Validate a pricing record's fields.

        Checks:
        - effective_from must not be None
        - effective_to must be None OR > effective_from
        - prompt_token_price >= 0
        - completion_token_price >= 0
        - cached_token_price >= 0 if not None
        - audio_token_price >= 0 if not None
        - image_price >= 0 if not None
        - embedding_price >= 0 if not None
        - currency must be non-empty
        - provider must be non-empty
        - model must be non-empty
        - version must be non-empty

        Raises PricingValidationError on any failure.
        """
        errors: list[str] = []

        # Required string fields
        if not pricing.provider or not pricing.provider.strip():
            errors.append("provider must be non-empty")
        if not pricing.model or not pricing.model.strip():
            errors.append("model must be non-empty")
        if not pricing.version or not pricing.version.strip():
            errors.append("version must be non-empty")
        if not pricing.currency or not pricing.currency.strip():
            errors.append("currency must be non-empty")

        # effective_from is required
        if pricing.effective_from is None:
            errors.append("effective_from must not be None")

        # effective_to must be after effective_from if set
        if (
            pricing.effective_from is not None
            and pricing.effective_to is not None
            and pricing.effective_to <= pricing.effective_from
        ):
            errors.append(
                f"effective_to ({pricing.effective_to}) must be after "
                f"effective_from ({pricing.effective_from})"
            )

        # Price fields must be non-negative
        _zero = Decimal(0)

        if pricing.prompt_token_price is None or pricing.prompt_token_price < _zero:
            errors.append("prompt_token_price must be >= 0")

        if pricing.completion_token_price is None or pricing.completion_token_price < _zero:
            errors.append("completion_token_price must be >= 0")

        if pricing.cached_token_price is not None and pricing.cached_token_price < _zero:
            errors.append("cached_token_price must be >= 0 if provided")

        if pricing.audio_token_price is not None and pricing.audio_token_price < _zero:
            errors.append("audio_token_price must be >= 0 if provided")

        if pricing.image_price is not None and pricing.image_price < _zero:
            errors.append("image_price must be >= 0 if provided")

        if pricing.embedding_price is not None and pricing.embedding_price < _zero:
            errors.append("embedding_price must be >= 0 if provided")

        if errors:
            raise PricingValidationError(f"Pricing validation failed: {'; '.join(errors)}")

        log.debug(
            "pricing_validated",
            provider=pricing.provider,
            model=pricing.model,
            version=pricing.version,
        )

    async def validate_no_overlap(
        self,
        repo: ModelPricingRepository,
        pricing: ModelPricing,
    ) -> None:
        """Check that no existing active pricing overlaps with the new date range.

        Fetches all versions for (provider, model) and checks for date range
        conflicts. Raises PricingValidationError if an overlap is detected.

        Note: does not check against the pricing record's own ID, so this can
        be called for both create and update operations.
        """
        existing_versions = await repo.list_for_model(pricing.provider, pricing.model)

        new_from = pricing.effective_from
        new_to = pricing.effective_to  # None = open-ended

        for existing in existing_versions:
            # Skip the same record (for updates)
            if existing.id == pricing.id:
                continue

            ex_from = existing.effective_from
            ex_to = existing.effective_to  # None = open-ended

            # Two date ranges overlap if: new_from <= ex_to AND ex_from <= new_to
            # With None treated as +infinity (open-ended)
            new_from_lte_ex_to = ex_to is None or new_from <= ex_to
            ex_from_lte_new_to = new_to is None or ex_from <= new_to

            if new_from_lte_ex_to and ex_from_lte_new_to:
                raise PricingValidationError(
                    f"Pricing for {pricing.provider}/{pricing.model} version "
                    f"'{existing.version}' overlaps with the new date range "
                    f"({new_from} to {new_to or 'open'}). "
                    f"Existing range: {ex_from} to {ex_to or 'open'}."
                )

        log.debug(
            "pricing_overlap_check_passed",
            provider=pricing.provider,
            model=pricing.model,
            effective_from=str(new_from),
            effective_to=str(new_to) if new_to else "open",
        )
