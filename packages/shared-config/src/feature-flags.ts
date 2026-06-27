/**
 * Feature flag keys — the names under which flags are stored in configuration.
 * All flags default to false in a fresh deployment.
 */
export const FeatureFlag = {
  /** Enable real-time WebSocket cost updates on the dashboard. */
  REALTIME_UPDATES: "realtime_updates",
  /** Enable AI-powered cost anomaly detection. */
  ANOMALY_DETECTION: "anomaly_detection",
  /** Enable the forecasting module. */
  FORECASTING: "forecasting",
  /** Enable multi-currency display. */
  MULTI_CURRENCY: "multi_currency",
  /** Enable self-service provider credential management. */
  PROVIDER_CREDENTIAL_MGMT: "provider_credential_mgmt",
} as const;

export type FeatureFlag = (typeof FeatureFlag)[keyof typeof FeatureFlag];

/** Runtime feature flag state. */
export type FeatureFlags = Readonly<Record<FeatureFlag, boolean>>;

/** All flags off — safe default for a fresh deployment. */
export const DEFAULT_FEATURE_FLAGS: FeatureFlags = Object.fromEntries(
  Object.values(FeatureFlag).map((key) => [key, false]),
) as FeatureFlags;
