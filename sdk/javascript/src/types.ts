/**
 * Shared type/catalog definitions.
 *
 * The provider catalog and UsageStatus values mirror
 * `backend/app/models/provider_connection.py::ProviderType` and
 * `backend/app/schemas/usage_ingestion.py::UsageStatus` (EP-16) exactly —
 * see `sdk/shared/API_CONTRACT.md`. This is a parallel, intentionally
 * matching definition, not a shared import: the SDK is an independently
 * distributable package and does not depend on the backend.
 */

export const SUPPORTED_PROVIDERS = [
  "openai",
  "anthropic",
  "grok",
  "google",
  "azure_openai",
  "openrouter",
  "ollama",
  "cohere",
  "bedrock",
  "mistral",
] as const;

export type Provider = (typeof SUPPORTED_PROVIDERS)[number];

export type UsageStatus = "success" | "error" | "timeout" | "cancelled";

/** Parameters for `Costorah.track()`. Field names are camelCase on the
 * public API; the SDK translates them to the snake_case wire format EP-16
 * expects (see `http.ts::buildPayload`). */
export interface TrackParams {
  // Widened to `string` (not just the `Provider` union) so a provider
  // added server-side before this SDK's next release still type-checks —
  // buildPayload() still validates it against SUPPORTED_PROVIDERS at
  // runtime.
  provider: Provider | string;
  model: string;
  inputTokens?: number;
  outputTokens?: number;
  cachedTokens?: number;
  totalTokens?: number;
  cost: number;
  currency?: string;
  latencyMs?: number;
  status?: UsageStatus;
  region?: string;
  projectId?: string;
  requestId?: string;
  timestamp?: Date;
  metadata?: Record<string, unknown>;
}

/** Result of a successful `track()` call. */
export interface TrackResult {
  success: boolean;
  usageId: string;
  requestId: string;
  processedAt: string;
  duplicate: boolean;
}
