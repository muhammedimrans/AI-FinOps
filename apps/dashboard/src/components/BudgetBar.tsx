import { motion } from "framer-motion";
import { cn, formatCost } from "../utils";

/** Server-derived 4-tier status (EP-24.2's BudgetEvaluationService) — when
 * supplied, this drives the bar's color instead of the pct-only 3-tier
 * heuristic below, so a caller with a real Budget's status never disagrees
 * with what the backend actually computed. */
export type BudgetBarStatus = "healthy" | "warning" | "critical" | "exceeded";

interface BudgetBarProps {
  used: number | string;
  total: number | string;
  pct: number;
  currency?: string;
  showLabels?: boolean;
  size?: "sm" | "md";
  status?: BudgetBarStatus;
}

export default function BudgetBar({
  used,
  total,
  pct,
  currency = "USD",
  showLabels = true,
  size = "md",
  status,
}: BudgetBarProps) {
  const clamped = Math.min(pct, 120);
  const overBudget = status ? status === "exceeded" : pct > 100;
  const nearBudget = status ? status === "warning" || status === "critical" : pct >= 80;

  const barColor = overBudget
    ? "bg-danger"
    : nearBudget
      ? "bg-warning"
      : "bg-success";

  const textColor = overBudget
    ? "text-danger"
    : nearBudget
      ? "text-warning"
      : "text-success";

  return (
    <div className="space-y-1.5">
      {showLabels && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-tx-muted">
            {formatCost(used, currency, true)} / {formatCost(total, currency, true)}
          </span>
          <span className={cn("text-xs font-semibold", textColor)}>
            {pct.toFixed(0)}%
          </span>
        </div>
      )}
      <div
        className={cn(
          "w-full rounded-full bg-app-muted overflow-hidden",
          size === "sm" ? "h-1.5" : "h-2",
        )}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(clamped, 100)}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={cn("h-full rounded-full", barColor)}
        />
      </div>
    </div>
  );
}
