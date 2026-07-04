import { useMemo } from "react";
import { useProjects, useTimeSeries } from "./useDashboard";
import { detectAnomalies } from "../lib/insights";
import { useNotificationStore } from "../stores/notifications";
import { useUIStore } from "../stores/ui";
import { useLiveActivity } from "../realtime/hooks";
import { formatCost, formatDate, formatDateTime } from "../utils";
import type { RealtimeEvent, RealtimeEventType } from "../realtime/types";

export type AlertSeverity = "danger" | "warning" | "info";

export interface DerivedAlert {
  /** Deterministic — read-state keys off this. For live events, this is the
   * event's own `event_id` (already globally unique). */
  id: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  category: "budget" | "anomaly" | "live";
  read: boolean;
  timestamp?: string;
  /** The persisted backend Alert's id, when this DerivedAlert originated
   * from a live event the EP-19.3 dispatcher fired (see
   * `AlertService._publish()`'s payload, which always includes
   * `alert_id`). Undefined for client-derived (budget/anomaly heuristic)
   * alerts, which have no backend row to acknowledge/resolve/archive via
   * the REST API — those can only be dismissed locally. */
  alertId?: string | undefined;
}

// Event types this panel treats as notification-worthy, matching the
// ticket's "Display: Budget warnings, Budget exceeded, Provider failures,
// Provider recovery, SDK connected, SDK disconnected, API Key events" list.
// usage.created/usage.updated are activity, not notifications — they have
// their own panel (LiveActivityFeed).
const NOTIFICATION_EVENT_TYPES: ReadonlySet<RealtimeEventType> = new Set([
  "budget.threshold_reached",
  "budget.exceeded",
  "provider.error",
  "provider.recovery",
  "api_key.created",
  "api_key.deleted",
  "sdk.connected",
  "sdk.disconnected",
  // EP-19.3: org_member_added/removed both ride on organization.updated
  // (see backend/app/alerts/dispatcher.py's _EVENT_TYPE_MAP) rather than
  // a dedicated event type — reusing what EP-19.1 already defined.
  "organization.updated",
  "notification.created",
]);

const EVENT_COPY: Partial<Record<RealtimeEventType, { severity: AlertSeverity; title: string }>> = {
  "budget.threshold_reached": { severity: "warning", title: "Budget threshold reached" },
  "budget.exceeded": { severity: "danger", title: "Budget exceeded" },
  "provider.error": { severity: "danger", title: "Provider error" },
  "provider.recovery": { severity: "info", title: "Provider recovered" },
  "api_key.created": { severity: "info", title: "API key created" },
  "api_key.deleted": { severity: "warning", title: "API key deleted" },
  "sdk.connected": { severity: "info", title: "SDK connected" },
  "sdk.disconnected": { severity: "warning", title: "SDK disconnected" },
  "organization.updated": { severity: "info", title: "Organization updated" },
  "notification.created": { severity: "info", title: "Notification" },
};

const SEVERITY_FROM_ALERT: Record<string, AlertSeverity> = {
  info: "info",
  low: "info",
  medium: "warning",
  high: "danger",
  critical: "danger",
};

/** Best-effort description from whatever fields a payload happens to carry
 * — these event types have no fixed payload shape defined yet on the
 * backend (only `usage.created` does; see docs/realtime/EVENT_MODEL.md's
 * honest accounting of what's actually emitted today), so this degrades
 * gracefully instead of assuming specific fields exist. */
function describePayload(event: RealtimeEvent): string {
  const payload = event.payload;
  const message = payload["message"] ?? payload["description"] ?? payload["reason"];
  if (typeof message === "string" && message.length > 0) return message;
  const name = payload["provider"] ?? payload["project_name"] ?? payload["name"];
  if (typeof name === "string" && name.length > 0) {
    return `${name} — ${formatDateTime(event.timestamp)}`;
  }
  return formatDateTime(event.timestamp);
}

function fromLiveEvent(event: RealtimeEvent): DerivedAlert {
  const copy = EVENT_COPY[event.type] ?? { severity: "info" as const, title: event.type };
  const alertId = event.payload["alert_id"];
  // AlertService._publish() always includes the persisted alert's own
  // title/severity — prefer those over the generic per-event-type copy
  // above when present, since they're specific ("acme@x.com joined the
  // organization") rather than generic ("Organization updated").
  const payloadTitle = event.payload["title"];
  const payloadSeverity = event.payload["severity"];
  const title = typeof payloadTitle === "string" && payloadTitle ? payloadTitle : copy.title;
  const severity =
    typeof payloadSeverity === "string" && SEVERITY_FROM_ALERT[payloadSeverity]
      ? SEVERITY_FROM_ALERT[payloadSeverity]
      : copy.severity;
  return {
    id: event.event_id,
    severity,
    title,
    description: describePayload(event),
    category: "live",
    read: false,
    timestamp: event.timestamp,
    alertId: typeof alertId === "string" ? alertId : undefined,
  };
}

/**
 * Alerts from two sources: budget/anomaly conditions derived from the live
 * dashboard data already in the query cache (unchanged from before this
 * EP), plus real-time notification-shaped events
 * (budget.threshold_reached/exceeded, provider.error/recovery, sdk.*,
 * api_key.*, notification.created) pushed over the EP-19.1 WebSocket.
 *
 * Honesty note (updated for EP-19.3): the backend's alert engine now
 * really fires budget.threshold_reached, budget.exceeded, and — via
 * organization.updated — org_member_added/removed and
 * api_key_created/revoked, off real ingestion and membership/API-key
 * mutations (see backend/docs/realtime/ALERT_ARCHITECTURE.md). The
 * remaining types in this map (provider.error/recovery, sdk.*) still have
 * no real trigger — no per-org provider-health signal or SDK heartbeat
 * tracking exists in this backend — and stay wired-but-dormant, exactly
 * as before.
 */
export function useAlerts(): { alerts: DerivedAlert[]; unreadCount: number } {
  const projects = useProjects();
  const timeSeries = useTimeSeries();
  const { currency } = useUIStore();
  const readIds = useNotificationStore((s) => s.readIds);
  const dismissedIds = useNotificationStore((s) => s.dismissedIds);
  const liveEvents = useLiveActivity();

  const alerts = useMemo<DerivedAlert[]>(() => {
    const out: DerivedAlert[] = [];

    for (const p of projects.data?.projects ?? []) {
      if (p.budget_utilization_pct > 100) {
        out.push({
          id: `budget-over:${p.project_id}`,
          severity: "danger",
          title: `${p.project_name} is over budget`,
          description: `${formatCost(p.total_cost, currency, true)} spent of ${formatCost(p.budget, currency, true)} (${p.budget_utilization_pct.toFixed(0)}%).`,
          category: "budget",
          read: false,
        });
      } else if (p.budget_utilization_pct >= 80) {
        out.push({
          id: `budget-near:${p.project_id}`,
          severity: "warning",
          title: `${p.project_name} approaching budget limit`,
          description: `${p.budget_utilization_pct.toFixed(0)}% of ${formatCost(p.budget, currency, true)} used.`,
          category: "budget",
          read: false,
        });
      }
    }

    const daily = (timeSeries.data?.data ?? []).map((d) => ({
      date: d.date,
      value: parseFloat(d.total_cost),
    }));
    for (const a of detectAnomalies(daily, { window: 7, threshold: 2 }).slice(-5)) {
      out.push({
        id: `anomaly:${a.date}`,
        severity: a.sigma > 0 ? "warning" : "info",
        title: `Spend anomaly on ${formatDate(a.date)}`,
        description: `${formatCost(a.value, currency, true)} — ${Number.isFinite(a.sigma) ? `${Math.abs(a.sigma).toFixed(1)}σ` : "sharply"} ${a.sigma > 0 ? "above" : "below"} the trailing average.`,
        category: "anomaly",
        read: false,
      });
    }

    for (const event of liveEvents) {
      if (NOTIFICATION_EVENT_TYPES.has(event.type)) out.push(fromLiveEvent(event));
    }

    return out
      .filter((a) => !dismissedIds[a.id])
      .map((a) => ({ ...a, read: !!readIds[a.id] }))
      .sort((a, b) => Number(a.read) - Number(b.read));
  }, [projects.data, timeSeries.data, currency, readIds, dismissedIds, liveEvents]);

  return { alerts, unreadCount: alerts.filter((a) => !a.read).length };
}
