import { useRef, useState } from "react";
import { Wifi, WifiOff, RefreshCw, ShieldAlert, Radio } from "lucide-react";
import { cn } from "../utils";
import { useConnectionStatus } from "../realtime/hooks";
import { useOrgStore } from "../stores/org";
import Popover from "./Popover";
import type { ConnectionStatus } from "../realtime/types";

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { label: string; icon: React.ElementType; dotClass: string; spin?: boolean }
> = {
  connected: { label: "Live", icon: Wifi, dotClass: "bg-success" },
  connecting: { label: "Connecting", icon: RefreshCw, dotClass: "bg-info", spin: true },
  reconnecting: { label: "Reconnecting", icon: RefreshCw, dotClass: "bg-warning", spin: true },
  offline: { label: "Offline", icon: WifiOff, dotClass: "bg-tx-muted" },
  auth_failed: { label: "Sign-in required", icon: ShieldAlert, dotClass: "bg-danger" },
  organization_changed: { label: "Switching organization", icon: Radio, dotClass: "bg-info" },
};

/**
 * Live-connection status pill for the header. Purely informational — the
 * dashboard works the same whether this reads "Live" or "Offline" (the
 * React Query bridge falls back to polling automatically), so this exists
 * to build trust in the live-updating numbers, not to gate functionality.
 */
export default function ConnectionIndicator() {
  const connection = useConnectionStatus();
  const organizationName = useOrgStore((s) => s.organizationName);
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);

  const { label, icon: Icon, dotClass, spin } = STATUS_CONFIG[connection.status];

  return (
    <div className="relative" ref={anchorRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`Real-time connection: ${label}`}
        className={cn(
          "btn-ghost h-8 px-2 gap-1.5 text-xs",
          open && "text-brand bg-app-hover",
        )}
      >
        <span className="relative flex size-2 flex-shrink-0" aria-hidden="true">
          {connection.status === "connected" && (
            <span
              className={cn("absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping", dotClass)}
            />
          )}
          <span className={cn("relative inline-flex size-2 rounded-full", dotClass)} />
        </span>
        <Icon size={13} className={cn("hidden sm:block", spin && "animate-spin")} />
        <span className="hidden sm:inline">{label}</span>
      </button>
      <Popover
        anchorRef={anchorRef}
        open={open}
        onClose={() => setOpen(false)}
        align="end"
        className="w-64 glass-card rounded-xl shadow-elevated z-[1000] p-4 origin-top-right"
      >
        <p className="text-sm font-semibold text-tx-primary mb-2">{label}</p>
        <dl className="flex flex-col gap-1.5 text-xs" role="status" aria-live="polite">
          <div className="flex items-center justify-between gap-2">
            <dt className="text-tx-muted">Organization</dt>
            <dd className="text-tx-secondary font-medium truncate max-w-[10rem]">
              {organizationName || "—"}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="text-tx-muted">Heartbeat latency</dt>
            <dd className="text-tx-secondary font-medium tabular-nums">
              {connection.heartbeatLatencyMs !== null ? `${connection.heartbeatLatencyMs} ms` : "—"}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="text-tx-muted">Reconnect attempts</dt>
            <dd className="text-tx-secondary font-medium tabular-nums">
              {connection.reconnectAttempts}
            </dd>
          </div>
          {connection.lastError && (
            <div className="pt-1.5 border-t border-border-subtle mt-1.5">
              <dt className="sr-only">Last error</dt>
              <dd className="text-tx-muted leading-relaxed">{connection.lastError}</dd>
            </div>
          )}
        </dl>
        <p className="text-[10px] text-tx-muted mt-3 leading-relaxed">
          {connection.status === "connected"
            ? "Dashboard numbers update live."
            : "Falling back to polling every 60s until reconnected."}
        </p>
      </Popover>
    </div>
  );
}
