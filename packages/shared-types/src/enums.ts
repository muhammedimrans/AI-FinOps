/** AI provider identifiers — canonical slug used across the platform. */
export enum Provider {
  OpenAI = "openai",
  Anthropic = "anthropic",
  Google = "google",
  XAI = "xai",
  OpenRouter = "openrouter",
  Local = "local",
  Unknown = "unknown",
}

/** Token classification for cost calculation. */
export enum TokenType {
  Input = "input",
  Output = "output",
  CachedInput = "cached_input",
  CachedOutput = "cached_output",
}

/** Modality of the AI call. */
export enum Modality {
  Text = "text",
  Image = "image",
  Audio = "audio",
  Video = "video",
  Embedding = "embedding",
  FineTuning = "fine_tuning",
}

/** Currency codes — ISO 4217. */
export enum Currency {
  USD = "USD",
  EUR = "EUR",
  GBP = "GBP",
}

/** Time granularity for aggregation queries. */
export enum TimeGranularity {
  Minute = "minute",
  Hour = "hour",
  Day = "day",
  Week = "week",
  Month = "month",
}

/** Lifecycle status of an entity. */
export enum Status {
  Active = "active",
  Inactive = "inactive",
  Pending = "pending",
  Archived = "archived",
}

/** Budget alert threshold types. */
export enum BudgetPeriod {
  Daily = "daily",
  Weekly = "weekly",
  Monthly = "monthly",
  Quarterly = "quarterly",
  Annual = "annual",
  Custom = "custom",
}

/** Reconciliation state of a usage event. */
export enum ReconciliationState {
  Provisional = "provisional",
  Reconciled = "reconciled",
  Disputed = "disputed",
}
