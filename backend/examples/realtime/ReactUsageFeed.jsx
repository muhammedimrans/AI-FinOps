// React example — EP-19.1.
//
// A minimal hook + component showing a live-updating feed of usage.created
// events. Uses native EventSource (no dependency), since dashboard clients
// are read-only consumers where SSE's built-in reconnect is the better fit
// than hand-rolling WebSocket reconnect logic — see docs/realtime/03-sse-guide.md.
//
// This file is illustrative, not wired into the actual AI-FinOps frontend —
// EP-19.1 is scoped to backend APIs only; frontend integration is EP-19.2's
// job (see the ticket's "Out of Scope" list).

import { useEffect, useRef, useState } from "react";

export function useRealtimeUsageFeed({ baseUrl, organizationId, token }) {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("connecting");
  const sourceRef = useRef(null);

  useEffect(() => {
    if (!organizationId || !token) return undefined;

    const url = `${baseUrl}/v1/events?organization_id=${organizationId}&token=${token}`;
    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => setStatus("connected");
    source.onerror = () => setStatus("reconnecting");

    source.addEventListener("usage.created", (event) => {
      const payload = JSON.parse(event.data);
      setEvents((prev) => [payload, ...prev].slice(0, 50));
    });

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [baseUrl, organizationId, token]);

  return { events, status };
}

export function UsageFeed({ baseUrl, organizationId, token }) {
  const { events, status } = useRealtimeUsageFeed({ baseUrl, organizationId, token });

  return (
    <div>
      <p>status: {status}</p>
      <ul>
        {events.map((event) => (
          <li key={event.event_id}>
            {event.payload.provider} / {event.payload.model} — {event.payload.cost}{" "}
            {event.payload.currency}
          </li>
        ))}
      </ul>
    </div>
  );
}
