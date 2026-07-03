/**
 * Best-effort cost calculation for responses that don't carry their own
 * cost figure. Mirrors the Python SDK's `costorah/instrumentation/
 * pricing.py` exactly (same table, same values, same "unknown model ->
 * cost 0, not estimated" honesty rule) — see that module's docstring for
 * why there's no real pricing *table* to import from the backend.
 */

const PRICE_PER_TOKEN: Record<string, [input: number, output: number]> = {
  "openai:gpt-4o": [0.0000025, 0.00001],
  "openai:gpt-4o-mini": [0.00000015, 0.0000006],
  "openai:gpt-4.1": [0.000002, 0.000008],
  "openai:gpt-4-turbo": [0.00001, 0.00003],
  "openai:gpt-3.5-turbo": [0.0000005, 0.0000015],
  "anthropic:claude-3-5-sonnet-20241022": [0.000003, 0.000015],
  "anthropic:claude-3-5-haiku-20241022": [0.0000008, 0.000004],
  "anthropic:claude-3-opus-20240229": [0.000015, 0.000075],
  "anthropic:claude-sonnet-4": [0.000003, 0.000015],
  "google:gemini-1.5-pro": [0.00000125, 0.000005],
  "google:gemini-1.5-flash": [0.000000075, 0.0000003],
  "google:gemini-2.0-flash": [0.0000001, 0.0000004],
  "mistral:mistral-large-latest": [0.000002, 0.000006],
  "mistral:mistral-small-latest": [0.0000001, 0.0000003],
  "cohere:command-r-plus": [0.0000025, 0.00001],
  "cohere:command-r": [0.00000015, 0.0000006],
};

export interface CostResult {
  cost: number;
  estimated: boolean;
}

/** Rounds to 8 decimal places, matching the backend PricingEngine's
 * convention (see pricing.py's docstring). */
function round8(value: number): number {
  return Math.round(value * 1e8) / 1e8;
}

export function calculateCost(
  provider: string,
  model: string,
  inputTokens: number,
  outputTokens: number,
): CostResult {
  const prices = PRICE_PER_TOKEN[`${provider}:${model}`];
  if (!prices) {
    return { cost: 0, estimated: false };
  }
  const [inputPrice, outputPrice] = prices;
  const inputCost = round8(inputTokens * inputPrice);
  const outputCost = round8(outputTokens * outputPrice);
  return { cost: round8(inputCost + outputCost), estimated: true };
}

export function hasPricing(provider: string, model: string): boolean {
  return `${provider}:${model}` in PRICE_PER_TOKEN;
}
