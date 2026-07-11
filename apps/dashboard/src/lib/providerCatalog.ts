import openaiLogo from "../assets/providers/openai.svg";
import anthropicLogo from "../assets/providers/anthropic.svg";
import googleGeminiLogo from "../assets/providers/google-gemini.svg";
import openrouterLogo from "../assets/providers/openrouter.svg";
import azureOpenaiLogo from "../assets/providers/azure-openai.svg";
import ollamaLogo from "../assets/providers/ollama.svg";
import grokLogo from "../assets/providers/grok.svg";
import deepseekLogo from "../assets/providers/deepseek.svg";
import llamaLogo from "../assets/providers/llama.svg";
import mistralLogo from "../assets/providers/mistral.svg";
import cohereLogo from "../assets/providers/cohere.svg";
import qwenLogo from "../assets/providers/qwen.svg";

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

// EP-26.0.2 — "Platform" / "Service" identity for providers whose backend
// ProviderType umbrella could one day cover more than one connectable
// surface. Today this only matters for Google: `ProviderType.GOOGLE`
// exclusively targets the AI Studio / Gemini Developer API (see
// GoogleProvider's own module docstring and CLAUDE.md's EP-26.0 Part 1) —
// Vertex AI Gemini is a distinct, not-yet-built future integration with a
// different auth model. This is a purely a *display* lookup, never a
// stored value (CLAUDE.md's EP-26.0 Part 4/Part 5 finding): if Vertex AI
// Gemini is ever added as a second connectable service under the same
// ProviderType.GOOGLE umbrella, that is the trigger to promote this into a
// real `ProviderConnection.configuration.platform` JSONB key — not before.
export interface ProviderPlatformInfo {
  platform: string;
  service: string;
}

export const PROVIDER_PLATFORM_INFO: Record<string, ProviderPlatformInfo> = {
  google: { platform: "AI Studio", service: "Gemini API" },
};

export function providerPlatformInfo(providerType: string): ProviderPlatformInfo | null {
  return PROVIDER_PLATFORM_INFO[providerType] ?? null;
}

// ─────────────────────────────────────────────────────────────────────────
// EP-26.0.4 — Centralized Provider Brand Registry.
//
// UI-only: purely a display concern (name/logo/website/platform/service/
// capability tags). Never touches the Provider Framework, the backend API,
// or ProviderConnection's schema — capabilities here are a short, cosmetic
// tag list for recognition, not sourced from any live capability-detection
// endpoint. Every logo asset is an SVG stored locally under
// src/assets/providers/ (never a CDN/hotlinked URL, never a raster PNG),
// imported once here and consumed everywhere else through this registry —
// no component imports a provider SVG directly (verified: `grep -rn
// "assets/providers"` outside this file returns nothing).
//
// `officialAsset: true` — an unmodified (only recolored to the brand's own
// published hex) SVG sourced from simple-icons (CC0-licensed icon
// recreations of real trademarks, npm package `simple-icons`, MIT/CC0),
// fetched from the public npm registry in this session. `officialAsset:
// false` — no redistributable official mark could be sourced for that
// provider in this environment (OpenAI, Azure, Grok/xAI, and Cohere have
// all been removed from simple-icons' own distribution, and this sandbox's
// network policy blocks direct access to each vendor's own brand-asset
// pages) — these four are original, unbranded geometric monograms in the
// provider's own published product color, disclosed here rather than
// silently presented as pixel-accurate trademarks. See CLAUDE.md's
// EP-26.0.4 section for the full sourcing methodology.
export interface ProviderBrand {
  id: string;
  displayName: string;
  logo: string;
  website: string;
  platform?: string;
  service?: string;
  capabilities: string[];
  officialAsset: boolean;
}

export const PROVIDER_BRAND_REGISTRY: Record<string, ProviderBrand> = {
  openai: {
    id: "openai",
    displayName: "OpenAI",
    logo: openaiLogo,
    website: "https://openai.com",
    service: "Chat Completions API",
    capabilities: ["Chat", "Vision", "Tools", "Streaming"],
    officialAsset: false,
  },
  anthropic: {
    id: "anthropic",
    displayName: "Anthropic",
    logo: anthropicLogo,
    website: "https://anthropic.com",
    service: "Claude API",
    capabilities: ["Chat", "Vision", "Tools", "Streaming"],
    officialAsset: true,
  },
  google: {
    id: "google",
    displayName: "Google Gemini",
    logo: googleGeminiLogo,
    website: "https://ai.google.dev",
    platform: "AI Studio",
    service: "Gemini API",
    capabilities: ["Chat", "Vision", "Audio", "Tools", "Streaming"],
    officialAsset: true,
  },
  openrouter: {
    id: "openrouter",
    displayName: "OpenRouter",
    logo: openrouterLogo,
    website: "https://openrouter.ai",
    service: "Unified Chat Completions Gateway",
    capabilities: ["Chat", "Vision", "Tools", "Streaming", "Multi-vendor"],
    officialAsset: true,
  },
  azure_openai: {
    id: "azure_openai",
    displayName: "Azure OpenAI",
    logo: azureOpenaiLogo,
    website: "https://azure.microsoft.com/products/ai-services/openai-service",
    platform: "Azure AI",
    service: "OpenAI Service",
    capabilities: ["Chat", "Vision", "Tools", "Streaming"],
    officialAsset: false,
  },
  grok: {
    id: "grok",
    displayName: "Grok (xAI)",
    logo: grokLogo,
    website: "https://x.ai",
    service: "Chat Completions API",
    capabilities: ["Chat", "Tools", "Streaming"],
    officialAsset: false,
  },
  ollama: {
    id: "ollama",
    displayName: "Ollama",
    logo: ollamaLogo,
    website: "https://ollama.com",
    service: "Local Model Runtime",
    capabilities: ["Chat", "Streaming", "Self-hosted"],
    officialAsset: true,
  },
  // Future-ready placeholders — registry entries only, per this EP's own
  // scope: no adapter, no connection type, no backend ProviderType member
  // exists for any of these five yet. Present so a future connectable
  // provider can be wired in without a second branding pass, and so
  // OpenRouter's underlying-vendor display (Analytics' Top Models table,
  // EP-26.0.1) can show a real logo for the vendor behind a routed model.
  deepseek: {
    id: "deepseek",
    displayName: "DeepSeek",
    logo: deepseekLogo,
    website: "https://deepseek.com",
    capabilities: ["Chat", "Tools", "Reasoning"],
    officialAsset: true,
  },
  llama: {
    id: "llama",
    displayName: "Meta Llama",
    logo: llamaLogo,
    website: "https://llama.meta.com",
    capabilities: ["Chat", "Tools", "Open-weight"],
    officialAsset: true,
  },
  mistral: {
    id: "mistral",
    displayName: "Mistral",
    logo: mistralLogo,
    website: "https://mistral.ai",
    capabilities: ["Chat", "Tools", "Streaming"],
    officialAsset: true,
  },
  cohere: {
    id: "cohere",
    displayName: "Cohere",
    logo: cohereLogo,
    website: "https://cohere.com",
    capabilities: ["Chat", "Embeddings", "Tools"],
    officialAsset: false,
  },
  qwen: {
    id: "qwen",
    displayName: "Qwen",
    logo: qwenLogo,
    website: "https://qwenlm.ai",
    capabilities: ["Chat", "Tools", "Open-weight"],
    officialAsset: true,
  },
};

// Aliases resolve every id/slug this codebase already uses for the same
// provider onto one canonical registry key — CONNECTABLE_PROVIDERS'
// backend-enum values ("azure_openai"), PROVIDER_CATALOG's shorter ids
// ("azure", "xai"), and OpenRouter's vendor slugs ("meta-llama", "x-ai",
// "mistralai") all resolve to the same brand entry, so every surface in
// the app looks up a provider's logo the same way regardless of which
// string shape that surface happens to already carry.
const PROVIDER_BRAND_ALIASES: Record<string, string> = {
  azure: "azure_openai",
  xai: "grok",
  "x-ai": "grok",
  "meta-llama": "llama",
  meta: "llama",
  mistralai: "mistral",
};

/**
 * Resolve a provider id/slug (any shape already used in this codebase —
 * ProviderType enum value, PROVIDER_CATALOG id, or an OpenRouter vendor
 * slug) to its brand entry. Always returns a value — an unrecognized id
 * falls back to a generic, logo-less entry (`ProviderLogo` renders a
 * neutral fallback glyph for this case, never a broken image).
 */
export function getProviderBrand(id: string): ProviderBrand {
  const key = id.toLowerCase();
  const resolved = PROVIDER_BRAND_REGISTRY[key] ?? PROVIDER_BRAND_REGISTRY[PROVIDER_BRAND_ALIASES[key] ?? ""];
  if (resolved) return resolved;
  return {
    id: key,
    displayName: connectableLabel(id) !== id ? connectableLabel(id) : id,
    logo: "",
    website: "",
    capabilities: [],
    officialAsset: false,
  };
}
