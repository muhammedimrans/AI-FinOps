# Examples

## Reading live events in a component

```tsx
import { useRealtimeEvent } from "../realtime/hooks";

function BudgetWatcher() {
  useRealtimeEvent("budget.exceeded", (event) => {
    // Not emitted by the backend yet (see docs/realtime/06-notifications.md)
    // — this still compiles and is ready the moment a later EP wires the trigger.
    console.log("Budget exceeded:", event.payload);
  });
  return null;
}
```

## Showing connection status

```tsx
import { useConnectionStatus } from "../realtime/hooks";

function MyStatusBadge() {
  const { status, reconnectAttempts } = useConnectionStatus();
  if (status === "connected") return <span>● Live</span>;
  if (status === "reconnecting") return <span>Reconnecting (attempt {reconnectAttempts})…</span>;
  return <span>Offline</span>;
}
```

See `frontend/src/components/ConnectionIndicator.tsx` for the real,
full-featured version used in the header.

## Getting the live activity buffer directly

```tsx
import { useLiveActivity } from "../realtime/hooks";

function LatestFive() {
  const events = useLiveActivity(5); // newest 5, newest first
  return (
    <ul>
      {events.map((e) => (
        <li key={e.event_id}>{e.type} at {e.timestamp}</li>
      ))}
    </ul>
  );
}
```

See `frontend/src/components/LiveActivityFeed.tsx` for the production
version (merges with the polled fallback, pause-on-hover, row cap).

## Making a query realtime-aware (the pattern every `useDashboard.ts` hook follows)

```ts
import { useQuery } from "@tanstack/react-query";
import { useRealtimeRefetchInterval } from "../realtime/hooks";

export function useMyDashboardData() {
  const refetchInterval = useRealtimeRefetchInterval(60_000);
  return useQuery({
    queryKey: ["my-data", /* ...filters */],
    queryFn: fetchMyData,
    refetchInterval, // false while connected, 60s otherwise
  });
}
```

Then add the query's key prefix to `USAGE_AFFECTED_QUERY_PREFIXES` in
`realtime/queryBridge.ts` if it should also refresh immediately (well,
within the 1.5s debounce window) on a live `usage.created` event.

## Full working reference

`frontend/src/features/Overview.tsx` is the most complete real example
in the repo — it uses `useConnectionStatus`, `useLiveMetrics`, and
`LiveActivityFeed` together, alongside its pre-existing (unmodified)
`useOverview`/`useTimeSeries`/`useProviders`/`useModels` calls.
