/**
 * @costorah/sdk — official JavaScript/TypeScript SDK for AI usage/cost
 * telemetry.
 *
 *     import { Costorah } from "@costorah/sdk";
 *
 *     const client = new Costorah({ apiKey: process.env.COSTORAH_API_KEY! });
 *     await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.041 });
 */

export { Costorah } from "./client.js";
export type { CostorahOptions, ResolvedConfig } from "./config.js";
export {
  AuthenticationError,
  ConfigurationError,
  CostorahError,
  NetworkError,
  RateLimitError,
  ServerError,
  ValidationError,
} from "./errors.js";
export { createConsoleLogger } from "./logging.js";
export type { Logger, LogLevel } from "./logging.js";
export { SUPPORTED_PROVIDERS } from "./types.js";
export type { Provider, TrackParams, TrackResult, UsageStatus } from "./types.js";
export { VERSION } from "./version.js";
