# Troubleshooting

## The connection indicator shows "Sign-in required"

The socket closed (or never opened) with an auth failure. Check:
- Is `useAuthStore().accessToken` actually populated? A logged-out
  session won't connect (this is expected, not a bug).
- Has the access token expired? `useRealtimeConnection` nudges a reconnect
  automatically once a refreshed token appears in the store, but only if
  the refresh itself succeeds — check the Network tab for
  `POST /v1/auth/refresh` failures.
- Is `?organization_id=` actually set? A JWT connection with no
  organization selected (`useOrgStore().organizationId === null`) never
  attempts to connect at all — `useRealtimeConnection` short-circuits in
  that case, which is why the indicator may simply show "Connecting"
  indefinitely rather than an error if you haven't picked an
  organization yet.

## The indicator is stuck on "Reconnecting"

Backoff caps at 30s between attempts (`connection.ts`'s
`reconnectDelayMs`), so a genuinely down backend/network will show this
for a while by design — it's still retrying, not stuck. Check the
Network/WS tab for the actual close code on each attempt; a repeating
4429 means the per-IP rate limiter
(`backend/app/realtime/rate_limit.py`) is being hit — likely from a
reconnect loop happening faster than intended, which would itself be a
bug worth investigating rather than the rate limiter being wrong.

## Numbers aren't updating even though the indicator says "Live"

1. **Only `usage.created` is actually emitted today.** If you're
   watching for a budget/provider/SDK/API-key event to move something on
   screen, it won't — see the honesty notes in
   [Notifications](./06-notifications.md) and the backend's
   [Event Model](../../backend/docs/realtime/04-event-model.md).
2. **Debounce window.** `useRealtimeQueryBridge` waits 1.5s of quiet
   after the last event before invalidating — a single event should
   still show up within ~1.5-2s, not instantly.
3. **Wrong organization.** Confirm the event actually belongs to the
   organization you're viewing — cross-organization delivery is
   architecturally impossible (see the backend's isolation guarantees),
   so if you're testing by publishing to a different org's id, nothing
   will arrive here, correctly.

## The activity feed or notification bell isn't reacting to hover/click

Check whether `AnimatePresence`/Framer Motion is disabled by
`prefers-reduced-motion` in your OS/browser settings — layout animations
are skipped in that mode (`<MotionConfig reducedMotion="user">`,
app-wide, EP-10), but click handlers and state updates still work
identically; only the animation is different, not the underlying
behavior. If interactions genuinely don't register, that's a real bug,
not a reduced-motion side effect.

## Switching organizations shows a flash of the previous organization's numbers

Should not happen — `resetForOrganizationChange()` clears
`recentActivity`/`lastEventByType`/`liveMetrics` synchronously before the
new connection opens (see
[Connection Lifecycle](./04-connection-lifecycle.md#organization-switching)).
If you do see stale data, check whether the polled React Query cache
(not the real-time store) still holds the previous organization's data
under a stale key — every `useDashboard.ts` query key includes
`organizationId`, so this would indicate a bug in that key construction,
not the real-time layer.

## Console warning: "act(...)" during tests

A handful of the frontend tests (`LiveActivityFeed.test.tsx`) log a
benign React Testing Library warning from the mocked
`getRecentActivity()` query resolving asynchronously after render — this
is a known, harmless RTL/React Query interaction, not a test failure
(all assertions pass). Not something to "fix" by suppressing the
warning; documented here so it isn't mistaken for a real problem during
review.
