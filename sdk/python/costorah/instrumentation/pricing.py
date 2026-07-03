"""
Best-effort cost calculation for responses that don't carry their own
cost figure (most provider SDKs return token counts, not dollars).

There is no reusable pricing *table* to import from the backend: COSTORAH's
own pricing catalog (`backend/app/models/model_pricing.py`) is a database
table with no seeded dollar values — organizations configure their own
prices via `POST /pricing/models`. What IS reusable is the backend's
calculation *convention* (`backend/app/pricing/engine.py::PricingEngine.
calculate_cost`): `Decimal` arithmetic, price-per-single-token, round each
component to 8 decimal places with ROUND_HALF_UP before summing, then
round the total the same way. This module mirrors that formula exactly
(a parallel implementation, not a shared import — the SDK does not depend
on the backend) and ships a small, honestly-labeled table of publicly
published list prices for common models as of this SDK's release.

If a model isn't in the table, cost is reported as 0.0 with
`metadata["cost_estimated"] = False` — never a fabricated or silently
wrong number. This mirrors the Monitoring Agent's OpenAI/Anthropic
collectors (EP-17), which report `cost=0.0` with a documented limitation
rather than guessing.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_QUANT = Decimal("0.00000001")  # matches PricingEngine's 8-decimal-place convention

# Publicly published list prices, USD per single token (i.e. per-1M-token
# list price / 1_000_000), as of this SDK's release. These are NOT pulled
# from COSTORAH's own pricing configuration (there is none to pull from —
# see module docstring) and may drift from a provider's current pricing.
# Treat this as a reasonable default for local dev/testing; configure
# COSTORAH's own pricing catalog for authoritative dashboard figures.
_PRICE_PER_TOKEN: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    # (provider, model): (input_price_per_token, output_price_per_token)
    ("openai", "gpt-4o"): (Decimal("0.0000025"), Decimal("0.00001")),
    ("openai", "gpt-4o-mini"): (Decimal("0.00000015"), Decimal("0.0000006")),
    ("openai", "gpt-4.1"): (Decimal("0.000002"), Decimal("0.000008")),
    ("openai", "gpt-4-turbo"): (Decimal("0.00001"), Decimal("0.00003")),
    ("openai", "gpt-3.5-turbo"): (Decimal("0.0000005"), Decimal("0.0000015")),
    ("anthropic", "claude-3-5-sonnet-20241022"): (Decimal("0.000003"), Decimal("0.000015")),
    ("anthropic", "claude-3-5-haiku-20241022"): (Decimal("0.0000008"), Decimal("0.000004")),
    ("anthropic", "claude-3-opus-20240229"): (Decimal("0.000015"), Decimal("0.000075")),
    ("anthropic", "claude-sonnet-4"): (Decimal("0.000003"), Decimal("0.000015")),
    ("google", "gemini-1.5-pro"): (Decimal("0.00000125"), Decimal("0.000005")),
    ("google", "gemini-1.5-flash"): (Decimal("0.000000075"), Decimal("0.0000003")),
    ("google", "gemini-2.0-flash"): (Decimal("0.0000001"), Decimal("0.0000004")),
    ("mistral", "mistral-large-latest"): (Decimal("0.000002"), Decimal("0.000006")),
    ("mistral", "mistral-small-latest"): (Decimal("0.0000001"), Decimal("0.0000003")),
    ("cohere", "command-r-plus"): (Decimal("0.0000025"), Decimal("0.00001")),
    ("cohere", "command-r"): (Decimal("0.00000015"), Decimal("0.0000006")),
}


def calculate_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> tuple[float, bool]:
    """Returns (cost, was_estimated). was_estimated is False when the
    model isn't in the table — cost is then 0.0, never a guess."""
    key = (provider, model)
    prices = _PRICE_PER_TOKEN.get(key)
    if prices is None:
        return 0.0, False

    input_price, output_price = prices
    input_cost = (Decimal(input_tokens) * input_price).quantize(_QUANT, rounding=ROUND_HALF_UP)
    output_cost = (Decimal(output_tokens) * output_price).quantize(_QUANT, rounding=ROUND_HALF_UP)
    total = (input_cost + output_cost).quantize(_QUANT, rounding=ROUND_HALF_UP)
    return float(total), True


def has_pricing(provider: str, model: str) -> bool:
    return (provider, model) in _PRICE_PER_TOKEN
