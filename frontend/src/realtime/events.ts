import { isRealtimeEvent, type RealtimeEvent, type RealtimeEventType } from "./types";

/**
 * Every event type this frontend knows how to route (matches the backend's
 * `EventType` enum, `app/realtime/events.py`). A value outside this set is
 * not an error — it's a future event type this build predates. Callers must
 * be able to receive it, ignore it safely, and keep running.
 */
export const KNOWN_EVENT_TYPES: readonly RealtimeEventType[] = [
  "usage.created",
  "usage.updated",
  "budget.threshold_reached",
  "budget.exceeded",
  "provider.error",
  "provider.recovery",
  "api_key.created",
  "api_key.deleted",
  "sdk.connected",
  "sdk.disconnected",
  "organization.updated",
  "notification.created",
];

export function isKnownEventType(type: string): type is RealtimeEventType {
  return (KNOWN_EVENT_TYPES as readonly string[]).includes(type);
}

/**
 * Parses one raw WebSocket/SSE text frame into a `RealtimeEvent`, or returns
 * `null` for anything that isn't one (malformed JSON, a `{"type":"ping"}`
 * heartbeat frame, or a shape that doesn't match the envelope). Never
 * throws — a single bad frame must never take down the connection.
 */
export function parseRealtimeFrame(raw: string): RealtimeEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRealtimeEvent(parsed)) return null;
  // An event for a type this build has never heard of is still a valid,
  // well-formed event — it's just routed nowhere. Don't reject it; a later
  // backend EP may start emitting it before this frontend build ships again.
  return parsed;
}
