/**
 * Wire types for the EP-19.1 backend real-time gateway (`GET /v1/ws`,
 * `GET /v1/events`). Mirrors `app/realtime/events.py`'s `RealtimeEvent`
 * envelope exactly — one shape, whichever transport carries it.
 */

/** The 12 event types the backend ticket named. Not all are emitted today —
 * see `docs/realtime/EVENT_MODEL.md` for which ones actually fire. Unknown
 * future values must never crash a consumer; treat this as open, not closed. */
export type RealtimeEventType =
  | "usage.created"
  | "usage.updated"
  | "budget.threshold_reached"
  | "budget.exceeded"
  | "provider.error"
  | "provider.recovery"
  | "api_key.created"
  | "api_key.deleted"
  | "sdk.connected"
  | "sdk.disconnected"
  | "organization.updated"
  | "notification.created";

export interface RealtimeEvent<TPayload = Record<string, unknown>> {
  event_id: string;
  timestamp: string;
  organization_id: string;
  type: RealtimeEventType;
  version: number;
  payload: TPayload;
  trace_id: string | null;
  correlation_id: string | null;
}

export interface UsageCreatedPayload {
  usage_id: string;
  provider: string;
  model: string;
  cost: string;
  currency: string;
  total_tokens: number;
  status: string;
  project_id: string | null;
}

/** Connection lifecycle states, matching the ticket's named states exactly. */
export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline"
  | "auth_failed"
  | "organization_changed";

export interface ConnectionSnapshot {
  status: ConnectionStatus;
  organizationId: string | null;
  reconnectAttempts: number;
  lastConnectedAt: number | null;
  lastHeartbeatAt: number | null;
  heartbeatLatencyMs: number | null;
  lastError: string | null;
}

/** A frame the client may send back over the WebSocket — currently only a
 * heartbeat reply; the server accepts any frame within the timeout window,
 * but sending a typed pong is the well-behaved-client convention documented
 * in the backend's WebSocket guide. */
export interface ClientPongFrame {
  type: "pong";
}

export function isRealtimeEvent(value: unknown): value is RealtimeEvent {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v["event_id"] === "string" &&
    typeof v["timestamp"] === "string" &&
    typeof v["organization_id"] === "string" &&
    typeof v["type"] === "string" &&
    typeof v["version"] === "number" &&
    typeof v["payload"] === "object" &&
    v["payload"] !== null
  );
}

export function isServerPing(value: unknown): value is { type: "ping" } {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<string, unknown>)["type"] === "ping"
  );
}
