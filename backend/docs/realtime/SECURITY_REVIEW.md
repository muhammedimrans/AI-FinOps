# Security Review — EP-19.1 Real-Time Telemetry Platform

Reviewed against the ticket's explicit checklist. Each item states what
was verified, how, and where the evidence lives.

## Cross-tenant isolation

**Verified.** `ConnectionManager.dispatch(organization_id, event)`
(`app/realtime/connection_manager.py`) only ever looks up
`self._by_org[organization_id]` — there is no code path that can hand one
organization's event to a connection registered under a different
`organization_id`. Confirmed at three layers:

1. Unit: `tests/test_ep19_1.py::TestConnectionManager::test_dispatch_delivers_only_to_matching_organization`
   — registers connections for org A and org B, dispatches to org A only,
   asserts org B's queue stays empty.
2. Integration (real WebSocket wire protocol):
   `TestWebSocketGateway::test_organization_isolation_over_the_wire`.
3. **Live, manual verification** against a running instance (see the
   final report's Verification Results): connected a WebSocket to org A,
   published an event for a different UUID directly through Redis, and
   confirmed nothing arrived on org A's socket within a 4-second window.

The replay buffer (`EventBus.replay_since`) is similarly keyed per
organization (`realtime:replay:<organization_id>`) — there is no shared
or global replay list a client could read across organizations.

## JWT validation

**Reused, not reimplemented.** `app/realtime/auth.py::_authenticate_jwt`
calls `app.auth.tokens.decode_access_token()` — the exact function every
other authenticated HTTP endpoint uses, with the same HS256 signature
check, `exp`/`iat`/`sub`/`jti` required-claims enforcement, and 30s clock
skew leeway. Additionally checks (also matching the existing
`get_current_user` HTTP dependency's behavior):

- Session revocation via `SessionRepository.get_active()` — a logged-out
  session's JWT is rejected even if not yet expired.
- User status — a `DISABLED` user's still-valid JWT is rejected.
- Organization membership and status — a user with no membership in the
  requested organization, or an organization that's suspended, is
  rejected.
- Role-based permission — `has_permission(membership.role, USAGE_READ)`.

Covered by `tests/test_ep19_1.py::TestAuthenticateRealtimeConnectionJwt`
(9 tests: valid connection, missing organization, revoked session,
disabled user, not a member, suspended organization, organization not
found, expired token, malformed token, and insufficient permission).

## API Key validation

**Reused, not reimplemented.** `_authenticate_api_key` calls
`ApiKeyAuthService.authenticate()` — the same service EP-15's HTTP API
Key dependency uses, including hash lookup (keys are never stored or
compared in plaintext), expiry check, and organization-suspended check.
Additionally checks the key's granted `permissions` list includes
`usage:read`, and that a supplied `?organization_id=` matches the key's
actual organization (rejecting `organization_mismatch` otherwise — this
prevents a key from being used to probe or join a different
organization's stream by simply passing a different id in the query
string). Covered by
`TestAuthenticateRealtimeConnectionApiKey` (6 tests).

## Replay resistance

The SSE replay buffer (`EventBus.replay_since`) is a read of an
organization-scoped Redis list, gated by the same
`authenticate_realtime_connection()` call every other part of this EP
uses — a client cannot request another organization's replay history
without a valid credential for that organization, and even a valid
credential can only ever request its own organization's buffer (the
`organization_id` used to key the replay lookup comes from the
authenticated `principal`, not from any client-supplied "replay for org
X" parameter — there is no such parameter). The buffer itself is
non-sensitive telemetry (usage metadata already visible to that
organization via the polling APIs), bounded to 200 entries / 1 hour, and
cannot be used to replay another organization's data under any input.

A stolen/leaked event id (the `event_id` UUID used as `Last-Event-ID`)
grants no additional access beyond a "resume from here" position within
the same authenticated organization's own buffer — it is not a
capability token and carries no auth weight itself.

## Connection exhaustion / DoS protection

- **Per-IP connection-attempt rate limiting**
  (`ConnectionRateLimiter`, 30 attempts/min by default, Redis-backed with
  in-memory fallback) applied to both `GET /v1/ws` (before `accept()`,
  closing with code `4429`) and `GET /v1/events` (before opening the
  stream, returning HTTP `429`). This limits attempts, not sustained
  connections — see the note below.
- **Bounded per-connection memory.** Every connection's outbound queue is
  capped at 256 events (`DEFAULT_QUEUE_MAXSIZE`); a malicious or
  misbehaving publisher cannot grow one connection's memory usage
  unboundedly by flooding events — excess events are dropped, not
  buffered.
- **Heartbeat-based stale-connection cleanup.** A connection that stops
  responding (10s timeout after a 30s ping) is closed, freeing its
  registration and queue rather than leaking it indefinitely.
- **What is not yet enforced**: a global cap on total concurrent
  connections (platform-wide or per-organization). The per-IP rate
  limiter throttles the *rate* of new connection attempts but does not
  cap how many connections one authenticated principal can hold open
  simultaneously (e.g. opening many tabs, or a script opening many
  connections with valid credentials faster than the rate limit's
  window rejects them, though still bounded by that window over time).
  This is a real, honestly-stated gap for a follow-up EP to close (a
  per-organization or per-principal concurrent-connection cap), not
  something silently assumed away — noted explicitly here rather than
  claimed as covered.

## Rate limiting

Verified via `tests/test_ep19_1.py::TestConnectionRateLimiter` (7 tests):
under-limit allowed, over-limit blocked, per-IP isolation (different IPs
tracked separately), Redis-backed path exercised via a mocked pipeline,
and — critically — a Redis outage degrades to the in-memory fallback
rather than failing open *or* failing closed in a way that would take
down connection handling.

## What this review does not claim

This is a code-level and integration-level review performed by the
implementer, not an independent third-party penetration test. No
external red-team exercise, fuzzing campaign, or adversarial load test
was run against a production-like deployment. The
"connection exhaustion" gap above is exactly the kind of finding that
kind of exercise would be expected to surface more of; this review
should be treated as a solid starting baseline, not a completed
security sign-off.
