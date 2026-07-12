import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell,
  BellOff,
  Check,
  Archive,
  RotateCcw,
  Filter,
  AlertOctagon,
  ShieldAlert,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import { useAlertsHistory, useAlertActions } from "../hooks/useAlertsHistory";
import type { AlertHistoryFilters } from "../hooks/useAlertsHistory";
import type { AlertApiSeverity, AlertApiStatus, AlertRecord } from "../services/api";
import { formatDateTime, cn } from "../utils";

const SEVERITY_BADGE: Record<AlertApiSeverity, string> = {
  info: "bg-info-dim text-info",
  low: "bg-app-muted text-tx-muted",
  medium: "bg-warning-dim text-warning",
  high: "bg-warning-dim text-warning border border-warning/40",
  critical: "bg-danger-dim text-danger",
};

const STATUS_BADGE: Record<AlertApiStatus, string> = {
  open: "bg-danger-dim text-danger",
  acknowledged: "bg-warning-dim text-warning",
  resolved: "bg-success-dim text-success",
  dismissed: "bg-app-muted text-tx-muted",
};

const SEVERITY_OPTIONS: AlertApiSeverity[] = ["critical", "high", "medium", "low", "info"];
const STATUS_OPTIONS: AlertApiStatus[] = ["open", "acknowledged", "resolved", "dismissed"];

function scopeFromMetadata(metadata: Record<string, unknown>): {
  project?: string;
  provider?: string;
  model?: string;
} {
  const project = typeof metadata["project_name"] === "string" ? metadata["project_name"] : undefined;
  const provider =
    typeof metadata["provider"] === "string"
      ? metadata["provider"]
      : typeof metadata["scope_provider"] === "string"
        ? metadata["scope_provider"]
        : undefined;
  const model =
    typeof metadata["model"] === "string"
      ? metadata["model"]
      : typeof metadata["scope_model"] === "string"
        ? metadata["scope_model"]
        : undefined;
  return { ...(project ? { project } : {}), ...(provider ? { provider } : {}), ...(model ? { model } : {}) };
}

function AlertRow({ alert }: { alert: AlertRecord }) {
  const { acknowledge, resolve, archive, reopen } = useAlertActions();
  const scope = scopeFromMetadata(alert.metadata);
  const busy = acknowledge.isPending || resolve.isPending || archive.isPending || reopen.isPending;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="rounded-xl border border-border-subtle bg-app-muted p-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={cn("badge text-[10px] font-semibold", SEVERITY_BADGE[alert.severity])}>
              {alert.severity}
            </span>
            <span className={cn("badge text-[10px] font-semibold", STATUS_BADGE[alert.status])}>
              {alert.status}
            </span>
            {alert.occurrence_count > 1 && (
              <span className="badge text-[10px] bg-app-bg text-tx-muted">
                ×{alert.occurrence_count}
              </span>
            )}
          </div>
          <p className="text-sm font-semibold text-tx-primary">{alert.title}</p>
          <p className="text-xs text-tx-secondary mt-0.5">{alert.message}</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[11px] text-tx-muted">
            <span>{formatDateTime(alert.last_occurred_at)}</span>
            {scope.project && <span>Project: {scope.project}</span>}
            {scope.provider && <span>Provider: {scope.provider}</span>}
            {scope.model && <span>Model: {scope.model}</span>}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {alert.status === "open" && (
            <>
              <button
                onClick={() => acknowledge.mutate({ alertId: alert.id })}
                disabled={busy}
                className="btn-outline h-7 px-2 text-[11px] inline-flex items-center gap-1"
              >
                <Check size={12} /> Acknowledge
              </button>
              <button
                onClick={() => resolve.mutate(alert.id)}
                disabled={busy}
                className="btn-primary h-7 px-2 text-[11px]"
              >
                Resolve
              </button>
            </>
          )}
          {alert.status === "acknowledged" && (
            <button
              onClick={() => resolve.mutate(alert.id)}
              disabled={busy}
              className="btn-primary h-7 px-2 text-[11px]"
            >
              Resolve
            </button>
          )}
          {(alert.status === "open" || alert.status === "acknowledged") && (
            <button
              onClick={() => archive.mutate(alert.id)}
              disabled={busy}
              className="icon-btn"
              aria-label="Dismiss alert"
            >
              <Archive size={14} />
            </button>
          )}
          {(alert.status === "resolved" || alert.status === "dismissed") && (
            <button
              onClick={() => reopen.mutate(alert.id)}
              disabled={busy}
              className="text-tx-muted hover:text-tx-primary inline-flex items-center gap-1 text-[11px]"
            >
              <RotateCcw size={12} /> Reopen
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function Alerts() {
  const [severity, setSeverity] = useState<AlertApiSeverity | "">("");
  const [status, setStatus] = useState<AlertApiStatus | "">("");
  const [search, setSearch] = useState("");

  const filters: AlertHistoryFilters = {
    ...(severity ? { severity } : {}),
    ...(status ? { status } : {}),
    ...(search ? { search } : {}),
  };
  const history = useAlertsHistory(filters);
  const alerts = history.data?.alerts ?? [];

  const openCount = alerts.filter((a) => a.status === "open").length;
  const criticalCount = alerts.filter((a) => a.severity === "critical" && a.status === "open").length;

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Alert Center"
        description="Budget threshold, spend spike, and system alerts fired by the notification engine."
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="glass-card rounded-card p-3 border border-border-subtle">
          <p className="text-[11px] text-tx-muted flex items-center gap-1">
            <Bell size={11} /> Open
          </p>
          <p className="text-lg font-bold text-tx-primary tabular-nums">{openCount}</p>
        </div>
        <div className="glass-card rounded-card p-3 border border-danger/30">
          <p className="text-[11px] text-danger flex items-center gap-1">
            <AlertOctagon size={11} /> Critical
          </p>
          <p className="text-lg font-bold text-danger tabular-nums">{criticalCount}</p>
        </div>
        <div className="glass-card rounded-card p-3 border border-border-subtle">
          <p className="text-[11px] text-tx-muted flex items-center gap-1">
            <ShieldAlert size={11} /> Total shown
          </p>
          <p className="text-lg font-bold text-tx-primary tabular-nums">{alerts.length}</p>
        </div>
        <div className="glass-card rounded-card p-3 border border-border-subtle">
          <p className="text-[11px] text-tx-muted flex items-center gap-1">
            <BellOff size={11} /> Resolved
          </p>
          <p className="text-lg font-bold text-tx-primary tabular-nums">
            {alerts.filter((a) => a.status === "resolved").length}
          </p>
        </div>
      </div>

      <Section
        title="Alert history"
        icon={Filter}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search alerts…"
              className="h-8 rounded-lg border border-border-subtle bg-app-bg px-3 text-xs text-tx-primary outline-none focus:border-brand w-40"
            />
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as AlertApiSeverity | "")}
              className="h-8 rounded-lg border border-border-subtle bg-app-bg px-2 text-xs text-tx-primary outline-none focus:border-brand"
              aria-label="Filter by severity"
            >
              <option value="">All severities</option>
              {SEVERITY_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as AlertApiStatus | "")}
              className="h-8 rounded-lg border border-border-subtle bg-app-bg px-2 text-xs text-tx-primary outline-none focus:border-brand"
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        }
      >
        {history.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }, (_, i) => <div key={i} className="h-20 skeleton rounded-xl" />)}
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState
            icon={Bell}
            title="No alerts"
            description="Nothing matches the current filters — or nothing has fired yet."
          />
        ) : (
          <div className="space-y-2">
            <AnimatePresence initial={false}>
              {alerts.map((a) => (
                <AlertRow key={a.id} alert={a} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </Section>
    </div>
  );
}
