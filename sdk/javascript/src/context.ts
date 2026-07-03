/**
 * Ambient request context — lets a framework integration (Express
 * middleware, etc.) attach request-scoped metadata (request ID, path,
 * method, organization) that automatically flows into every usage event
 * submitted during that request, without every instrumented call needing
 * to pass it explicitly.
 *
 * Backed by Node's `AsyncLocalStorage`, the standard primitive for
 * per-async-call-chain context (the JS equivalent of Python's
 * `contextvars`) — correct under concurrent requests handled on the same
 * event loop.
 */

import { AsyncLocalStorage } from "node:async_hooks";

const storage = new AsyncLocalStorage<Record<string, unknown>>();

/** The current request's ambient metadata, or undefined outside a
 * request (e.g. a background job, or no framework integration in use). */
export function getRequestContext(): Record<string, unknown> | undefined {
  return storage.getStore();
}

/** Runs `fn` with ambient metadata set for its entire async call chain.
 * Framework middleware wraps each request in this; nothing else needs to
 * call it directly under normal use. */
export function runWithRequestContext<T>(
  fields: Record<string, unknown>,
  fn: () => T,
): T {
  return storage.run(fields, fn);
}
