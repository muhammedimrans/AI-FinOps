import { AnimatePresence, motion } from "framer-motion";
import { OctagonAlert } from "lucide-react";
import { useAlerts } from "../hooks/useAlerts";
import { useNotificationStore } from "../stores/notifications";

/**
 * A dismissible banner for unread danger-severity alerts (budget exceeded,
 * a critical live-fired alert, etc.) — the ticket's "critical banner"
 * dashboard-integration item. Additive: reuses `useAlerts()` exactly as
 * the notification center does, no dashboard rewrite, no new data source.
 */
export default function CriticalAlertBanner() {
  const { alerts } = useAlerts();
  const { dismiss } = useNotificationStore();
  const critical = alerts.filter((a) => a.severity === "danger" && !a.read);

  if (critical.length === 0) return null;
  const [first, ...rest] = critical;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: "auto" }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.2 }}
        role="alert"
        className="flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger-dim px-3.5 py-2.5"
      >
        <OctagonAlert size={16} className="text-danger flex-shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-tx-primary">{first!.title}</p>
          <p className="text-[11px] text-tx-muted mt-0.5 leading-relaxed">{first!.description}</p>
          {rest.length > 0 && (
            <p className="text-[10px] text-tx-muted mt-1">
              +{rest.length} more critical alert{rest.length === 1 ? "" : "s"} — see the bell menu.
            </p>
          )}
        </div>
        <button
          onClick={() => dismiss(first!.id)}
          className="text-[11px] font-medium text-danger hover:text-danger-light flex-shrink-0"
        >
          Dismiss
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
