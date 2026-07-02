import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "../utils";

interface SectionProps {
  title?: string;
  description?: string;
  icon?: React.ElementType;
  iconClassName?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

/**
 * Standard card wrapper for non-chart content (tables, lists, forms) — the
 * counterpart to ChartCard, which additionally handles chart loading/error/
 * legend states. Consistent glass-card + top accent line + header row used
 * across every feature page.
 */
export default function Section({
  title,
  description,
  icon: Icon,
  iconClassName,
  actions,
  children,
  className,
  bodyClassName,
}: SectionProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "glass-card rounded-card-lg border border-border-subtle relative overflow-hidden",
        className,
      )}
    >
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />

      {(title || actions) && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            {title && (
              <h3 className="text-sm font-semibold text-tx-primary flex items-center gap-2">
                {Icon && <Icon size={14} className={cn("text-tx-muted flex-shrink-0", iconClassName)} />}
                {title}
              </h3>
            )}
            {description && <p className="text-xs text-tx-muted mt-0.5">{description}</p>}
          </div>
          {actions && (
            <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto sm:flex-shrink-0">
              {actions}
            </div>
          )}
        </div>
      )}

      <div className={cn(!title && !actions ? "p-5" : "", bodyClassName)}>{children}</div>
    </motion.div>
  );
}
