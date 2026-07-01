import { forwardRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from "lucide-react";
import { useToastStore, type Toast, type ToastVariant } from "../stores/toast";
import { cn } from "../utils";

const VARIANT_CONFIG: Record<ToastVariant, { icon: React.ElementType; iconClass: string; borderClass: string }> = {
  success: { icon: CheckCircle2, iconClass: "text-success", borderClass: "border-success/25" },
  error:   { icon: XCircle,      iconClass: "text-danger",  borderClass: "border-danger/25" },
  warning: { icon: AlertTriangle, iconClass: "text-warning", borderClass: "border-warning/25" },
  info:    { icon: Info,         iconClass: "text-info",    borderClass: "border-info/25" },
};

// forwardRef is required here: AnimatePresence mode="popLayout" measures each
// exiting child via a ref, which only works if the immediate child of
// AnimatePresence can accept one — a plain function component can't.
const ToastItem = forwardRef<HTMLDivElement, { toast: Toast }>(function ToastItem({ toast }, ref) {
  const dismiss = useToastStore((s) => s.dismiss);
  const { icon: Icon, iconClass, borderClass } = VARIANT_CONFIG[toast.variant];

  useEffect(() => {
    const timer = setTimeout(() => dismiss(toast.id), toast.duration);
    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, dismiss]);

  return (
    <motion.div
      ref={ref}
      layout
      role="status"
      aria-live="polite"
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 64, scale: 0.95, transition: { duration: 0.15 } }}
      transition={{ type: "spring", stiffness: 400, damping: 32 }}
      className={cn(
        "glass-panel pointer-events-auto flex items-start gap-3 w-full max-w-sm p-4 border",
        borderClass,
      )}
    >
      <Icon size={18} className={cn("flex-shrink-0 mt-0.5", iconClass)} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-tx-primary">{toast.title}</p>
        {toast.description && (
          <p className="text-xs text-tx-secondary mt-0.5 leading-relaxed">{toast.description}</p>
        )}
      </div>
      <button
        onClick={() => dismiss(toast.id)}
        aria-label="Dismiss notification"
        className="flex-shrink-0 text-tx-muted hover:text-tx-primary transition-colors duration-fast"
      >
        <X size={15} />
      </button>
    </motion.div>
  );
});

/** Mount once (in AppLayout). Renders toasts pushed via the `toast` helper from stores/toast.ts. */
export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);

  return (
    <div
      className="fixed bottom-4 right-4 z-[300] flex flex-col gap-2 pointer-events-none w-full max-w-sm px-4 sm:px-0"
      aria-label="Notifications"
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} />
        ))}
      </AnimatePresence>
    </div>
  );
}
