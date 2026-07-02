import { useMemo } from "react";
import { useProjects, useTimeSeries } from "./useDashboard";
import { detectAnomalies } from "../lib/insights";
import { useNotificationStore } from "../stores/notifications";
import { useUIStore } from "../stores/ui";
import { formatCost, formatDate } from "../utils";

export type AlertSeverity = "danger" | "warning" | "info";

export interface DerivedAlert {
  /** Deterministic — read-state keys off this. */
  id: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  category: "budget" | "anomaly";
  read: boolean;
}

/**
 * Alerts derived from the live dashboard data already in the query cache:
 * budget overruns/warnings from project data, spend anomalies from the daily
 * time series. When a server-side notification feed ships, this hook swaps
 * its data source without any consumer changes.
 */
export function useAlerts(): { alerts: DerivedAlert[]; unreadCount: number } {
  const projects = useProjects();
  const timeSeries = useTimeSeries();
  const { currency } = useUIStore();
  const readIds = useNotificationStore((s) => s.readIds);

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

    return out
      .map((a) => ({ ...a, read: !!readIds[a.id] }))
      .sort((a, b) => Number(a.read) - Number(b.read));
  }, [projects.data, timeSeries.data, currency, readIds]);

  return { alerts, unreadCount: alerts.filter((a) => !a.read).length };
}
