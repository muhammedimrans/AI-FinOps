import type { Currency } from "@costorah/shared-types";

/** Runtime environment. */
export type AppEnvironment = "development" | "staging" | "production" | "testing";

/** Log level. */
export type LogLevel = "debug" | "info" | "warning" | "error" | "critical";

/** Top-level application configuration shape. */
export interface AppConfig {
  readonly env: AppEnvironment;
  readonly debug: boolean;
  readonly logLevel: LogLevel;
  readonly defaultCurrency: Currency;
  readonly apiBaseUrl: string;
  readonly apiVersion: string;
}

/** Default values used in development. */
export const DEFAULT_APP_CONFIG: Readonly<Omit<AppConfig, "apiBaseUrl">> = {
  env: "development",
  debug: false,
  logLevel: "info",
  defaultCurrency: "USD" as Currency,
  apiVersion: "v1",
} as const;
