import { describe, expect, it } from "vitest";
import { isKnownEventType, KNOWN_EVENT_TYPES, parseRealtimeFrame } from "../events";

function makeEventJson(overrides: Partial<Record<string, unknown>> = {}): string {
  return JSON.stringify({
    event_id: "11111111-1111-1111-1111-111111111111",
    timestamp: "2026-07-03T12:00:00Z",
    organization_id: "org-1",
    type: "usage.created",
    version: 1,
    payload: { provider: "openai" },
    trace_id: null,
    correlation_id: null,
    ...overrides,
  });
}

describe("KNOWN_EVENT_TYPES / isKnownEventType", () => {
  it("has exactly the 12 backend-defined event types", () => {
    expect(KNOWN_EVENT_TYPES).toHaveLength(12);
    expect(KNOWN_EVENT_TYPES).toContain("usage.created");
    expect(KNOWN_EVENT_TYPES).toContain("notification.created");
  });

  it("rejects a type this build has never heard of", () => {
    expect(isKnownEventType("some.future.type")).toBe(false);
  });
});

describe("parseRealtimeFrame", () => {
  it("parses a well-formed event", () => {
    const event = parseRealtimeFrame(makeEventJson());
    expect(event).not.toBeNull();
    expect(event?.type).toBe("usage.created");
    expect(event?.organization_id).toBe("org-1");
  });

  it("returns null for malformed JSON without throwing", () => {
    expect(() => parseRealtimeFrame("{not valid json")).not.toThrow();
    expect(parseRealtimeFrame("{not valid json")).toBeNull();
  });

  it("returns null for a heartbeat ping frame", () => {
    expect(parseRealtimeFrame(JSON.stringify({ type: "ping" }))).toBeNull();
  });

  it("returns null for an object missing required envelope fields", () => {
    expect(parseRealtimeFrame(JSON.stringify({ type: "usage.created" }))).toBeNull();
  });

  it("still parses an event of a type this build doesn't recognize — unknown types are valid, just unrouted", () => {
    const event = parseRealtimeFrame(makeEventJson({ type: "some.future.type" }));
    expect(event).not.toBeNull();
    expect(event?.type).toBe("some.future.type");
  });

  it("returns null for a JSON array (not an object)", () => {
    expect(parseRealtimeFrame("[1,2,3]")).toBeNull();
  });

  it("returns null for a JSON primitive", () => {
    expect(parseRealtimeFrame("42")).toBeNull();
    expect(parseRealtimeFrame('"just a string"')).toBeNull();
  });
});
