/**
 * Structured logging with mandatory secret redaction — the SDK must never
 * log an API key, a prompt, a model response, or other sensitive
 * metadata, even at debug level. Mirrors the Python SDK's `_logging.py`
 * and the Monitoring Agent's `logging_setup.py` (EP-17) so the whole
 * COSTORAH ecosystem redacts consistently.
 */

const REDACTED_KEY_PATTERNS = [
  "apikey",
  "api_key",
  "authorization",
  "password",
  "secret",
  "token",
  "prompt",
  "completion",
  "responsebody",
  "response_body",
  "userprompt",
  "user_prompt",
  "modelresponse",
  "model_response",
];

const BEARER_TOKEN_RE = /costorah_live_[A-Za-z0-9_-]+/g;

function redactString(value: string): string {
  return value.replace(BEARER_TOKEN_RE, "costorah_live_***REDACTED***");
}

/** Recursively redact known-sensitive keys and any embedded
 * costorah_live_ token substring, regardless of which field it's in. */
export function redact(value: unknown): unknown {
  if (typeof value === "string") {
    return redactString(value);
  }
  if (Array.isArray(value)) {
    return value.map(redact);
  }
  if (value !== null && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value)) {
      const lowered = key.toLowerCase();
      if (REDACTED_KEY_PATTERNS.some((pattern) => lowered.includes(pattern))) {
        result[key] = "***REDACTED***";
      } else {
        result[key] = redact(val);
      }
    }
    return result;
  }
  return value;
}

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface Logger {
  debug(message: string, fields?: Record<string, unknown>): void;
  info(message: string, fields?: Record<string, unknown>): void;
  warn(message: string, fields?: Record<string, unknown>): void;
  error(message: string, fields?: Record<string, unknown>): void;
}

const LEVEL_ORDER: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };

/** A minimal structured console logger with redaction baked in. Callers
 * may supply their own `Logger` implementation (e.g. to route into pino
 * or winston) as long as it redacts consistently — the SDK always calls
 * `redact()` before handing fields to whichever logger is configured, so
 * even a caller-supplied logger receives already-redacted data. */
export function createConsoleLogger(level: LogLevel = "info"): Logger {
  const threshold = LEVEL_ORDER[level];
  const emit = (lvl: LogLevel, message: string, fields?: Record<string, unknown>): void => {
    if (LEVEL_ORDER[lvl] < threshold) return;
    const safeFields = fields ? redact(fields) : undefined;
    const line = `[costorah] ${lvl.toUpperCase()} ${message}`;
    // eslint-disable-next-line no-console
    const consoleMethod = lvl === "error" ? console.error : lvl === "warn" ? console.warn : console.log;
    if (safeFields) {
      consoleMethod(line, safeFields);
    } else {
      consoleMethod(line);
    }
  };

  return {
    debug: (message, fields) => emit("debug", message, fields),
    info: (message, fields) => emit("info", message, fields),
    warn: (message, fields) => emit("warn", message, fields),
    error: (message, fields) => emit("error", message, fields),
  };
}
