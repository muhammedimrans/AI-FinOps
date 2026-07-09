import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Clock } from "lucide-react";
import ProviderBadge from "./ProviderBadge";
import Section from "./Section";
import { cn, formatCost, formatDateTime, formatNumber, modelDisplayName } from "../utils";
import { useLiveActivity, useConnectionStatus } from "../realtime/hooks";
import { useRecentActivity } from "../hooks/useDashboard";
import { useUIStore } from "../stores/ui";
import type { RealtimeEvent, UsageCreatedPayload } from "../realtime/types";

interface ActivityRow {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  cost: number;
  status: string;
}

function fromLiveEvent(event: RealtimeEvent): ActivityRow {
  const payload = event.payload as unknown as UsageCreatedPayload;
  return {
    id: event.event_id,
    timestamp: event.timestamp,
    provider: payload.provider,
    model: payload.model,
    cost: Number.parseFloat(payload.cost) || 0,
    status: payload.status,
  };
}

const STATUS_CLASS: Record<string, string> = {
  success: "text-success bg-success-dim",
  error: "text-danger bg-danger-dim",
  timeout: "text-warning bg-warning-dim",
  cancelled: "text-tx-muted bg-app-muted",
};

// Visible rows are capped rather than run through a windowing/virtualization
// library — the underlying buffer (RealtimeStore.recentActivity) can hold up
// to `activityLimit` (200) events, but only this many are ever mounted in the
// DOM at once, which is the practical performance mitigation for a list this
// size. True virtualization would need a new dependency this repo doesn't
// otherwise use; documented here rather than claimed.
const MAX_VISIBLE_ROWS = 25;

interface LiveActivityFeedProps {
  limit?: number;
}

/**
 * "Recent Activity" panel — live over WebSocket when connected, falling
 * back to the polled endpoint's data otherwise (which currently returns
 * an empty list; see docs/realtime/troubleshooting.md). Newest first,
 * pauses on hover so a reader isn't fighting the list to click a row.
 */
export default function LiveActivityFeed({ limit = MAX_VISIBLE_ROWS }: LiveActivityFeedProps) {
  const { currency } = useUIStore();
  const connection = useConnectionStatus();
  const liveEvents = useLiveActivity(limit);
  const polled = useRecentActivity(limit);
  const [paused, setPaused] = useState(false);
  const [frozenRows, setFrozenRows] = useState<ActivityRow[] | null>(null);

  const liveRows = liveEvents.filter((e) => e.type === "usage.created").map(fromLiveEvent);

  const polledRows: ActivityRow[] = (polled.data?.events ?? []).map((e) => ({
    id: e.id,
    timestamp: e.timestamp,
    provider: e.provider,
    model: e.model_id,
    cost: Number.parseFloat(e.cost) || 0,
    status: "success",
  }));

  const liveRowIds = new Set(liveRows.map((r) => r.id));
  const rows = [...liveRows, ...polledRows.filter((r) => !liveRowIds.has(r.id))].slice(0, limit);

  const displayRows = paused ? (frozenRows ?? rows) : rows;

  function handleMouseEnter() {
    setFrozenRows(rows);
    setPaused(true);
  }
  function handleMouseLeave() {
    setPaused(false);
    setFrozenRows(null);
  }

  const isLive = connection.status === "connected";

  return (
    <Section
      title="Recent Activity"
      description="Latest AI API calls across all providers"
      icon={Clock}
      actions={
        <div className="flex items-center gap-1.5" aria-live="polite">
          <span className="relative flex w-2 h-2" aria-hidden="true">
            {isLive && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75" />
            )}
            <span className={cn("relative inline-flex rounded-full w-2 h-2", isLive ? "bg-success" : "bg-tx-muted")} />
          </span>
          <span className="text-xs text-tx-muted">{isLive ? "Live" : "Polling"}</span>
        </div>
      }
    >
      <div
        className="overflow-x-auto"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <table className="w-full data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Provider</th>
              <th>Model</th>
              <th>Status</th>
              <th className="text-right">Cost</th>
            </tr>
          </thead>
          <tbody>
            {polled.isLoading && rows.length === 0
              ? Array.from({ length: 6 }, (_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 5 }, (_, j) => (
                      <td key={j}>
                        <div className="h-4 skeleton rounded w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              : displayRows.length === 0
                ? (
                  <tr>
                    <td colSpan={5} className="text-center text-tx-muted text-xs py-8">
                      No activity yet — new requests will appear here instantly.
                    </td>
                  </tr>
                )
                : (
                  <AnimatePresence initial={false}>
                    {displayRows.map((row, i) => (
                      <motion.tr
                        key={row.id}
                        layout
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.25, delay: Math.min(i * 0.02, 0.2) }}
                      >
                        <td className="text-tx-muted whitespace-nowrap">{formatDateTime(row.timestamp)}</td>
                        <td>
                          <ProviderBadge provider={row.provider} size="sm" />
                        </td>
                        <td className="text-tx-primary font-mono text-xs">{modelDisplayName(row.model)}</td>
                        <td>
                          <span
                            className={cn(
                              "text-[10px] font-semibold px-1.5 py-0.5 rounded-full capitalize",
                              STATUS_CLASS[row.status] ?? "text-tx-muted bg-app-muted",
                            )}
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="text-right font-semibold text-xs text-tx-primary tabular-nums">
                          {formatCost(row.cost, currency)}
                        </td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                )}
          </tbody>
        </table>
      </div>
      {rows.length > 0 && (
        <p className="text-[10px] text-tx-muted px-1 pt-2">
          Showing the {formatNumber(displayRows.length)} most recent{paused ? " (paused — move away to resume)" : ""}.
        </p>
      )}
    </Section>
  );
}
