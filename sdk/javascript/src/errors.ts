/**
 * SDK-specific errors. Every failure mode raised by `Costorah.track()` is
 * one of these — never a bare fetch/network exception — so calling code
 * can catch `CostorahAuthenticationError` etc. without needing to know the
 * SDK's transport.
 *
 * See `sdk/shared/API_CONTRACT.md` for the HTTP-status -> error mapping
 * every COSTORAH SDK implements identically.
 */

export class CostorahError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CostorahError";
  }
}

export class ConfigurationError extends CostorahError {
  constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
}

/** 401/403 — invalid/expired key, suspended organization, or a key
 * missing the `usage:write` scope. Not retried: this is a client
 * configuration problem, not a transient failure. */
export class AuthenticationError extends CostorahError {
  statusCode: number | undefined;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "AuthenticationError";
    this.statusCode = statusCode;
  }
}

/** 400/404/422 — the payload itself was rejected. Not retried: an
 * unchanged payload can never succeed no matter how many times it's
 * resent. */
export class ValidationError extends CostorahError {
  statusCode: number | undefined;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "ValidationError";
    this.statusCode = statusCode;
  }
}

/** 429 — retried with backoff, honoring Retry-After if the server sends
 * one. */
export class RateLimitError extends CostorahError {
  statusCode: number | undefined;
  retryAfter: number | undefined;

  constructor(message: string, statusCode?: number, retryAfter?: number) {
    super(message);
    this.name = "RateLimitError";
    this.statusCode = statusCode;
    this.retryAfter = retryAfter;
  }
}

/** 5xx from the ingestion API. Retried with exponential backoff. */
export class ServerError extends CostorahError {
  statusCode: number | undefined;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "ServerError";
    this.statusCode = statusCode;
  }
}

/** No response was received at all (timeout, connection refused, DNS
 * failure, TLS error, ...). Retried with exponential backoff. */
export class NetworkError extends CostorahError {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}
