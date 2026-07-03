from __future__ import annotations

from costorah.instrumentation.pricing import calculate_cost, has_pricing


def test_known_model_returns_computed_cost_and_estimated_true() -> None:
    cost, estimated = calculate_cost("openai", "gpt-4o", 1_000_000, 0)
    assert estimated is True
    assert cost == 2.5  # 1,000,000 * $0.0000025/token


def test_known_model_combines_input_and_output_cost() -> None:
    cost, estimated = calculate_cost("openai", "gpt-4o-mini", 1000, 1000)
    assert estimated is True
    # (1000 * 0.00000015) + (1000 * 0.0000006)
    assert round(cost, 10) == round(0.00015 + 0.0006, 10)


def test_unknown_model_returns_zero_cost_not_estimated() -> None:
    cost, estimated = calculate_cost("openai", "not-a-real-model", 1000, 1000)
    assert cost == 0.0
    assert estimated is False


def test_unknown_provider_returns_zero_cost_not_estimated() -> None:
    cost, estimated = calculate_cost("not-a-real-provider", "gpt-4o", 1000, 1000)
    assert cost == 0.0
    assert estimated is False


def test_zero_tokens_yields_zero_cost_even_for_known_model() -> None:
    cost, estimated = calculate_cost("anthropic", "claude-3-5-sonnet-20241022", 0, 0)
    assert cost == 0.0
    assert estimated is True  # the model IS priced; there's just nothing to charge for


def test_has_pricing_reflects_table_membership() -> None:
    assert has_pricing("openai", "gpt-4o") is True
    assert has_pricing("openai", "not-a-real-model") is False
    assert has_pricing("ollama", "llama3") is False
