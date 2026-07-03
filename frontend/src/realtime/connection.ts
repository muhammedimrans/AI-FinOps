/**
 * Pure connection helpers — URL construction and reconnect backoff.
 * Kept dependency-free from `WebSocket`/React so they're trivially unit
 * testable and reusable if a future EP adds an SSE fallback client here.
 */

const DEFAULT_BASE_URL: string =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

/** `http(s)://...` → `ws(s)://...`, since the backend's WS gateway lives on
 * the same host/port as the REST API — no separate real-time host. */
function toWebSocketOrigin(httpBaseUrl: string): string {
  return httpBaseUrl.replace(/^http/, "ws");
}

export interface BuildWsUrlOptions {
  baseUrl?: string;
  token: string;
  organizationId: string;
}

/** Browser `WebSocket` cannot set an `Authorization` header on the
 * handshake — the token has to travel as `?token=`, exactly as
 * `app/realtime/auth.py::extract_token()` expects as its fallback. */
export function buildWebSocketUrl({
  baseUrl = DEFAULT_BASE_URL,
  token,
  organizationId,
}: BuildWsUrlOptions): string {
  const url = new URL("/v1/ws", toWebSocketOrigin(baseUrl));
  url.searchParams.set("organization_id", organizationId);
  url.searchParams.set("token", token);
  return url.toString();
}

const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;
const JITTER_RATIO = 0.2;

/**
 * Exponential backoff with jitter, capped at `MAX_DELAY_MS`. `attempt` is
 * 0-indexed (the first reconnect attempt after a drop is `attempt=0`).
 * Jitter is deterministic-free (uses `Math.random`) by design — a fleet of
 * clients reconnecting after a shared outage should not all retry in
 * lockstep.
 */
export function reconnectDelayMs(attempt: number, random: () => number = Math.random): number {
  const exponential = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  const jitter = exponential * JITTER_RATIO * (random() * 2 - 1);
  return Math.max(0, Math.round(exponential + jitter));
}

/** Close codes the backend gateway uses (`docs/realtime/02-websocket-guide.md`
 * on the backend) — used to decide whether a close is worth retrying. */
export const WS_CLOSE_RATE_LIMITED = 4429;
export const WS_CLOSE_AUTH_FAILED = 4401;
export const WS_CLOSE_HEARTBEAT_TIMEOUT = 4408;
export const WS_CLOSE_NORMAL = 1000;

/** Auth failures should not be retried with backoff forever — the token
 * needs to actually change (e.g. a refresh, a re-login) first. Every other
 * close is treated as transient and worth reconnecting. */
export function isRetryableCloseCode(code: number): boolean {
  return code !== WS_CLOSE_AUTH_FAILED;
}
