# Authentication — Real-Time Connections

**No new auth system.** `app/realtime/auth.py` calls the exact same
validation functions the existing HTTP dependencies use — it does not
re-implement JWT decoding, session-revocation checking, API-key hashing,
or membership/RBAC lookup.

| Concern | Function reused | From |
|---|---|---|
| JWT decode + signature/expiry check | `decode_access_token()` | `app.auth.tokens` |
| Session revocation check | `SessionRepository.get_active()` | `app.repositories.session_repository` |
| API Key hash lookup + expiry + org status | `ApiKeyAuthService.authenticate()` | `app.services.api_key_auth_service` |
| Role → permission check | `has_permission()` | `app.auth.rbac` |
| API Key scope check | `ApiKeyAuthContext.has_permission()` | `app.services.api_key_auth_service` |

## What's actually new

Only the "last mile": pulling a raw token string out of a WebSocket
handshake or an SSE `GET` request, since neither can use FastAPI's
`Security(oauth2_scheme)` / `Header()` machinery the way a normal HTTP
route does, and opening one short-lived database session for the check
(`authenticate_realtime_connection()` uses
`async with container.session_factory() as db: ...` — the same primitive
`get_db()` itself wraps — rather than holding a request-scoped session
for a connection's entire, potentially hours-long lifetime).

## Token extraction

`extract_token()` checks, in order:

1. `Authorization: Bearer <token>` header
2. `?token=<token>` query parameter

A browser `WebSocket`/`EventSource` cannot set custom headers on its
handshake request, so the query-parameter form exists specifically for
them. Server-side clients (this EP's Python example clients, the CLI
listener) should prefer the header form — it doesn't end up in access
logs or browser history the way a query string can.

## Distinguishing a JWT from an API Key

The same rule the existing `app.auth.api_key_auth._looks_like_api_key`
uses: an API Key always starts with `costorah_live_`. Anything else is
treated as a JWT and passed to `decode_access_token()`.

## Required permission

Opening a real-time connection requires `Permission.USAGE_READ` — the
same permission the existing `GET /v1/usage/*` polling endpoints require.
No new `Permission.REALTIME_READ` was added, since a real-time stream is
the streaming equivalent of what those endpoints already expose: any
organization member (any role, since `USAGE_READ` is in every role's
default permission set) and any API Key granted the `usage:read` scope
can connect.

## Organization resolution

- **API Key**: the key belongs to exactly one organization
  (`ApiKeyAuthContext.organization_id`). If the connection also passes
  `?organization_id=`, it must match — otherwise the connection is
  rejected with `organization_mismatch`.
- **JWT**: a user can belong to multiple organizations, so
  `?organization_id=` is **required**. The connection is rejected with
  `missing_organization` if it's absent, `organization_not_found` if the
  id doesn't exist, `not_a_member` if the authenticated user has no
  membership in it, and `organization_inactive` if the organization is
  suspended.

## Failure reasons

Every failure raises `RealtimeAuthError` with one of these reasons
(`RealtimeAuthErrorReason` in `app/realtime/auth.py`), which the gateway
endpoints translate into a WS close code or an SSE HTTP status:

`missing_token`, `invalid_token`, `expired_token`, `user_disabled`,
`missing_organization`, `organization_not_found`,
`organization_inactive`, `not_a_member`, `insufficient_permissions`,
`organization_mismatch`.

## Organization isolation

This is the property the security review in
[`SECURITY_REVIEW.md`](./SECURITY_REVIEW.md) verifies directly:
`ConnectionManager.dispatch()` only ever looks up connections in
`self._by_org[organization_id]` — there is no code path in
`dispatch()`, `register()`, or `receive()` that can hand one
organization's `RealtimeEvent` to a connection registered under a
different `organization_id`. `tests/test_ep19_1.py::TestConnectionManager::test_dispatch_delivers_only_to_matching_organization`
and `TestWebSocketGateway::test_organization_isolation_over_the_wire`
assert this directly, including over the real WebSocket wire protocol.
