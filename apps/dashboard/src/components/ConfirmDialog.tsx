import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Loader2 } from "lucide-react";
import { cn } from "../utils";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Generic destructive-action confirmation modal — reused wherever a delete/remove needs a guard. */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = true,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // Focus only on the open transition — depending on onCancel/loading here
  // would re-run this (and steal focus back) on every parent re-render.
  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !loading) onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, loading, onCancel]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center px-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={loading ? undefined : onCancel}
            aria-hidden="true"
          />
          <motion.div
            ref={dialogRef}
            tabIndex={-1}
            role="alertdialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.97 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="relative w-full max-w-sm glass-panel shadow-elevated p-6"
          >
            <div className="flex items-start gap-3 mb-4">
              <div
                className={cn(
                  "w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0",
                  danger ? "bg-danger-dim text-danger" : "bg-brand-subtle text-brand",
                )}
              >
                <AlertTriangle size={16} />
              </div>
              <div className="min-w-0 pt-1">
                <h2 className="text-sm font-semibold text-tx-primary">{title}</h2>
                {description && (
                  <p className="text-xs text-tx-muted mt-1 leading-relaxed">{description}</p>
                )}
              </div>
            </div>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={onCancel}
                disabled={loading}
                className="btn-outline h-9 text-xs px-3.5"
              >
                {cancelLabel}
              </button>
              <button
                onClick={onConfirm}
                disabled={loading}
                className={cn(
                  "h-9 text-xs px-3.5 rounded-lg font-semibold flex items-center gap-1.5 transition-colors duration-fast",
                  danger
                    ? "bg-danger text-white hover:bg-danger-light disabled:opacity-60"
                    : "btn-primary",
                )}
              >
                {loading && <Loader2 size={13} className="animate-spin" />}
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
