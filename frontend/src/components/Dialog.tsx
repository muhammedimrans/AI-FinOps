import { useEffect, useRef, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "../utils";

interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  closeOnBackdrop?: boolean;
  maxWidthClassName?: string;
  children: ReactNode;
}

/**
 * Generic modal chrome (backdrop, focus trap, Escape-to-close) — the form/
 * content counterpart to ConfirmDialog, which is reserved for yes/no
 * destructive-action confirmations.
 */
export default function Dialog({
  open,
  title,
  onClose,
  closeOnBackdrop = true,
  maxWidthClassName = "max-w-md",
  children,
}: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // Focus only on the open transition — depending on onClose here would
  // re-run this (and steal focus back from any input inside) on every
  // keystroke, since callers typically pass a fresh inline closure.
  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center px-4 py-8 overflow-y-auto">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={closeOnBackdrop ? onClose : undefined}
            aria-hidden="true"
          />
          <motion.div
            ref={dialogRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.97 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className={cn(
              "relative w-full glass-panel shadow-elevated p-6 my-auto",
              maxWidthClassName,
            )}
          >
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
