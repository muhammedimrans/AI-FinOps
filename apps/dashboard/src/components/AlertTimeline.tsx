import { motion } from "framer-motion";
import { CheckCircle2, Circle, PlayCircle, XCircle } from "lucide-react";
import { cn, formatDateTime } from "../utils";
import type { AlertRecord } from "../services/api";

interface TimelineStep {
  key: string;
  label: string;
  timestamp: string;
  icon: React.ElementType;
  className: string;
  detail?: string | null;
}

/**
 * Chronological Created → Acknowledged → Resolved/Dismissed timeline for one
 * persisted alert. Reopen is not a distinct step here: the backend Alert
 * row doesn't keep a full append-only history (see
 * backend/docs/realtime/ALERT_ARCHITECTURE.md's "Timeline note"), so a
 * reopened alert's earlier acknowledged/resolved timestamps stay visible
 * (an honest "this happened, then it was reopened") rather than being
 * hidden or fabricated as a second cycle.
 */
export default function AlertTimeline({ alert }: { alert: AlertRecord }) {
  const steps: TimelineStep[] = [
    {
      key: "created",
      label: "Created",
      timestamp: alert.first_occurred_at,
      icon: Circle,
      className: "text-info",
    },
  ];

  if (alert.acknowledged_at) {
    steps.push({
      key: "acknowledged",
      label: "Acknowledged",
      timestamp: alert.acknowledged_at,
      icon: PlayCircle,
      className: "text-warning",
      detail: alert.acknowledgement_reason,
    });
  }
  if (alert.resolved_at) {
    steps.push({
      key: "resolved",
      label: "Resolved",
      timestamp: alert.resolved_at,
      icon: CheckCircle2,
      className: "text-success",
    });
  }
  if (alert.dismissed_at) {
    steps.push({
      key: "dismissed",
      label: "Dismissed",
      timestamp: alert.dismissed_at,
      icon: XCircle,
      className: "text-tx-muted",
    });
  }

  steps.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  return (
    <ol className="relative pl-5" aria-label={`Timeline for ${alert.title}`}>
      {steps.map((step, i) => {
        const Icon = step.icon;
        const isLast = i === steps.length - 1;
        return (
          <motion.li
            key={step.key}
            className="relative pb-4 last:pb-0"
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2, delay: i * 0.05 }}
          >
            {!isLast && (
              <span
                aria-hidden="true"
                className="absolute left-[-15px] top-4 bottom-0 w-px bg-border-subtle"
              />
            )}
            <Icon size={14} className={cn("absolute left-[-20px] top-0.5", step.className)} />
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium text-tx-primary">{step.label}</span>
              <span className="text-[10px] text-tx-muted tabular-nums">
                {formatDateTime(step.timestamp)}
              </span>
            </div>
            {step.detail && (
              <p className="text-[11px] text-tx-muted mt-0.5 leading-relaxed">{step.detail}</p>
            )}
          </motion.li>
        );
      })}
    </ol>
  );
}
