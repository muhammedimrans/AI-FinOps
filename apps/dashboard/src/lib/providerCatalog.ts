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

// EP-24.3 — mirrors the backend's ProviderSyncService._KNOWN_USAGE_API_PROVIDERS
// exactly: purely informational (which providers have a real bulk
// usage-history API today), never a gate on whether sync can run — every
// connectable provider syncs through the identical pipeline regardless.
export const KNOWN_USAGE_API_PROVIDERS = new Set(["openai", "anthropic"]);

export function hasKnownUsageApi(providerType: string): boolean {
  return KNOWN_USAGE_API_PROVIDERS.has(providerType);
}
