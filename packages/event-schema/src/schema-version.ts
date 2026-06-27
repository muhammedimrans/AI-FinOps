/** Current schema version — bump on any breaking change to UsageEvent. */
export const EVENT_SCHEMA_VERSION = "1.0.0" as const;
export type EventSchemaVersion = typeof EVENT_SCHEMA_VERSION;
