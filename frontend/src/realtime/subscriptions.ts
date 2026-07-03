import { RealtimeClient } from "./client";
import { useRealtimeStore } from "./store";
import type { ConnectionSnapshot, RealtimeEvent, RealtimeEventType } from "./types";

type Listener = (event: RealtimeEvent) => void;

/**
 * Owns the single `RealtimeClient` for the whole app and fans incoming
 * events out to per-type listeners, in addition to feeding the shared
 * `RealtimeStore`. There is exactly one real-time connection per app
 * instance — it's joined to one organization, matching the backend's model
 * — so this is a module singleton rather than something instantiated per
 * component, the same way `useRealtimeStore` itself is a singleton.
 *
 * "Subscribing" here is purely local event-type routing: the backend has no
 * per-type subscribe/unsubscribe protocol (every event for the joined
 * organization flows to the one connection — see EP-19.1's connection
 * manager docs), so a "subscription" is just a JS callback registered
 * against a type, never a message sent over the wire.
 */
class RealtimeSubscriptionManager {
  private client: RealtimeClient | null = null;
  private listenersByType = new Map<RealtimeEventType | "*", Set<Listener>>();
  private currentOrganizationId: string | null = null;
  private currentGetToken: (() => string | null) | null = null;

  /** Starts (or restarts, if already running under a different
   * organization/token) the connection. Safe to call repeatedly with the
   * same arguments — it no-ops rather than reconnecting needlessly. */
  start(getToken: () => string | null, organizationId: string): void {
    if (this.client && this.currentOrganizationId === organizationId) {
      // Token may have rotated (refresh) — the client re-reads it via
      // `getToken` on its next reconnect, so just keep the same socket
      // running; nothing to do here.
      this.currentGetToken = getToken;
      return;
    }

    this.stop();
    this.currentOrganizationId = organizationId;
    this.currentGetToken = getToken;
    useRealtimeStore.getState().resetForOrganizationChange();

    this.client = new RealtimeClient({
      getToken,
      organizationId,
      onEvent: (event) => this.dispatch(event),
      onStatusChange: (snapshot) => useRealtimeStore.getState().setConnection(snapshot),
    });
    this.client.connect();
  }

  stop(): void {
    this.client?.disconnect();
    this.client = null;
    this.currentOrganizationId = null;
    this.currentGetToken = null;
  }

  /** Forces a fresh connection attempt now (e.g. right after a token
   * refresh completed, so an `auth_failed` connection doesn't sit idle
   * until its next scheduled retry). */
  reconnectNow(): void {
    this.client?.reconnectNow();
  }

  getSnapshot(): ConnectionSnapshot | null {
    return this.client?.getSnapshot() ?? null;
  }

  /** Subscribe to one event type, or `"*"` for every event. Returns an
   * unsubscribe function — call it from a `useEffect` cleanup. */
  subscribe(type: RealtimeEventType | "*", listener: Listener): () => void {
    let set = this.listenersByType.get(type);
    if (!set) {
      set = new Set();
      this.listenersByType.set(type, set);
    }
    set.add(listener);
    return () => {
      set?.delete(listener);
    };
  }

  private dispatch(event: RealtimeEvent): void {
    useRealtimeStore.getState().ingestEvent(event);
    for (const listener of this.listenersByType.get(event.type) ?? []) listener(event);
    for (const listener of this.listenersByType.get("*") ?? []) listener(event);
  }
}

export const realtimeSubscriptions = new RealtimeSubscriptionManager();
