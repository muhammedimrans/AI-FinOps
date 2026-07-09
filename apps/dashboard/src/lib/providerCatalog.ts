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
