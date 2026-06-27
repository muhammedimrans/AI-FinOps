/** Top-level error category. Maps to HTTP status class. */
export enum ErrorCategory {
  /** 4xx — caller made a bad request. */
  Client = "CLIENT",
  /** 401/403 — auth failures. */
  Auth = "AUTH",
  /** 404 — resource not found. */
  NotFound = "NOT_FOUND",
  /** 409 — state conflict. */
  Conflict = "CONFLICT",
  /** 429 — caller exceeded rate limits. */
  RateLimit = "RATE_LIMIT",
  /** 5xx — platform-side failure. */
  Server = "SERVER",
  /** Provider-side failure (proxied). */
  Provider = "PROVIDER",
  /** Schema / validation failure. */
  Validation = "VALIDATION",
}
