// Full catalog of AI providers the Costorah UI can display. Only the ids in
// `SUPPORTED_PROVIDER_IDS` are backed by real backend cost data — the rest
// render as "not connected" placeholders so the Providers page reflects the
// full ecosystem without fabricating spend/usage numbers for integrations
// the backend doesn't track yet.
export interface ProviderCatalogEntry {
  id: string;
  name: string;
  color: string;
}

export const PROVIDER_CATALOG: ProviderCatalogEntry[] = [
  { id: "openai", name: "OpenAI", color: "#10A37F" },
  { id: "anthropic", name: "Anthropic", color: "#D4A574" },
  { id: "google", name: "Google Gemini", color: "#4285F4" },
  { id: "azure", name: "Azure OpenAI", color: "#0078D4" },
  { id: "bedrock", name: "AWS Bedrock", color: "#FF9900" },
  { id: "cohere", name: "Cohere", color: "#9B5DE5" },
  { id: "groq", name: "Groq", color: "#F55036" },
  { id: "mistral", name: "Mistral", color: "#FF7000" },
  { id: "deepseek", name: "DeepSeek", color: "#4D6BFE" },
  { id: "together", name: "Together AI", color: "#0F6FFF" },
  { id: "fireworks", name: "Fireworks AI", color: "#6420FF" },
  { id: "openrouter", name: "OpenRouter", color: "#6467F2" },
  { id: "ollama", name: "Ollama", color: "#000000" },
  { id: "xai", name: "xAI", color: "#000000" },
  { id: "huggingface", name: "Hugging Face", color: "#FFD21E" },
  { id: "perplexity", name: "Perplexity", color: "#1FB8CD" },
  { id: "cerebras", name: "Cerebras", color: "#F15A29" },
  { id: "replicate", name: "Replicate", color: "#000000" },
  { id: "sambanova", name: "SambaNova", color: "#EE7624" },
  { id: "nvidia-nim", name: "NVIDIA NIM", color: "#76B900" },
];

// The subset the FastAPI backend currently reports real cost/usage data for.
// Keep in sync with types/api.ts's `Provider` union.
export const SUPPORTED_PROVIDER_IDS = new Set([
  "openai",
  "anthropic",
  "google",
  "azure",
  "bedrock",
  "cohere",
]);

// Chart/badge accent color per provider id — single source of truth, derived
// from the catalog so badge dots, pie slices, and bars always agree.
export const PROVIDER_COLORS: Record<string, string> = Object.fromEntries(
  PROVIDER_CATALOG.map((p) => [p.id, p.color]),
);

// EP-22 — the 7 providers the product spec calls "supported": persisted,
// customer-managed connection *records* (name, type, active/inactive,
// health). Values match backend ProviderType exactly (some differ from
// PROVIDER_CATALOG's ids — e.g. "azure_openai" not "azure", "grok" not "xai").
// Shared by features/Connections.tsx and features/Onboarding.tsx (EP-21.3).
export const CONNECTABLE_PROVIDERS: { value: string; label: string; color: string }[] = [
  { value: "openai", label: "OpenAI", color: PROVIDER_COLORS["openai"] ?? "#888" },
  { value: "anthropic", label: "Anthropic", color: PROVIDER_COLORS["anthropic"] ?? "#888" },
  { value: "google", label: "Google Gemini", color: PROVIDER_COLORS["google"] ?? "#888" },
  { value: "openrouter", label: "OpenRouter", color: PROVIDER_COLORS["openrouter"] ?? "#888" },
  { value: "azure_openai", label: "Azure OpenAI", color: PROVIDER_COLORS["azure"] ?? "#888" },
  { value: "grok", label: "Grok (xAI)", color: PROVIDER_COLORS["xai"] ?? "#888" },
  { value: "ollama", label: "Ollama", color: PROVIDER_COLORS["ollama"] ?? "#888" },
];

export function connectableLabel(providerType: string): string {
  return CONNECTABLE_PROVIDERS.find((p) => p.value === providerType)?.label ?? providerType;
}

// EP-24.3/EP-26.0.1 — mirrors the backend's
// ProviderSyncService._KNOWN_USAGE_API_PROVIDERS exactly: purely
// informational (which providers have a real bulk usage-history API
// today), never a gate on whether sync can run — every connectable
// provider syncs through the identical pipeline regardless. "openrouter"
// added in EP-26.0.1 (GET /api/v1/activity) — see CLAUDE.md's EP-26.0.1
// section for the disclosed uncertainty around that endpoint's exact
// credential requirements.
export const KNOWN_USAGE_API_PROVIDERS = new Set(["openai", "anthropic", "openrouter"]);

export function hasKnownUsageApi(providerType: string): boolean {
  return KNOWN_USAGE_API_PROVIDERS.has(providerType);
}

// EP-26.0.1 — OpenRouter model identifiers are "vendor/model" slugs (e.g.
// "anthropic/claude-sonnet-4"); this is a pure display-layer parse of an
// already-correct, already-stored string (CLAUDE.md's EP-26.0 Part 2/
// EP-26.0.1 "Data Mapping" finding: no schema change needed to store this,
// only to display the vendor/model split).
const OPENROUTER_VENDOR_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
  "meta-llama": "Meta",
  meta: "Meta",
  deepseek: "DeepSeek",
  mistralai: "Mistral",
  qwen: "Qwen",
  "x-ai": "xAI",
  xai: "xAI",
  cohere: "Cohere",
  microsoft: "Microsoft",
  amazon: "Amazon",
};

export interface ParsedOpenRouterModel {
  vendorSlug: string;
  vendorLabel: string;
  modelSlug: string;
}

export function parseOpenRouterModelId(modelId: string): ParsedOpenRouterModel | null {
  const slashIndex = modelId.indexOf("/");
  if (slashIndex <= 0 || slashIndex === modelId.length - 1) {
    return null;
  }
  const vendorSlug = modelId.slice(0, slashIndex);
  const modelSlug = modelId.slice(slashIndex + 1);
  return {
    vendorSlug,
    vendorLabel: OPENROUTER_VENDOR_LABELS[vendorSlug.toLowerCase()] ?? vendorSlug,
    modelSlug,
  };
}
