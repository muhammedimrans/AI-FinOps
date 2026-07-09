import { ReactNode } from "react";
import { motion } from "framer-motion";
import { BarChart3 } from "lucide-react";
import { cn } from "../utils";

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
  legend?: ReactNode;
  loading?: boolean;
  error?: string | null;
  /** True when the query succeeded but returned no rows for the period. */
  empty?: boolean;
  emptyMessage?: string;
  /** EP-22.3 — replaces the default "No data for this period" empty state
   * entirely with contextual, actionable guidance (e.g. "Connect Provider")
   * when provided. Falls back to the generic ChartEmpty when omitted. */
  emptyContent?: ReactNode;
  className?: string;
  bodyClassName?: string;
  minHeight?: number;
}

function ChartSkeleton({ height }: { height: number }) {
  return (
    <div className="w-full flex flex-col gap-2" style={{ height }}>
      <div className="flex items-end gap-1 h-full px-2 pb-4">
        {Array.from({ length: 14 }, (_, i) => (
          <div
            key={i}
            className="skeleton flex-1 rounded-t"
            style={{ height: `${30 + Math.sin(i * 0.7) * 40 + 20}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function ChartEmpty({ height, message }: { height: number; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6" style={{ height }}>
      <div className="w-10 h-10 rounded-xl bg-app-muted flex items-center justify-center mb-3">
        <BarChart3 size={18} className="text-tx-muted" />
      </div>
      <p className="text-sm font-medium text-tx-primary mb-0.5">No data for this period</p>
      <p className="text-xs text-tx-muted leading-relaxed max-w-xs">{message}</p>
    </div>
  );
}

export default function ChartCard({
  title,
  subtitle,
  children,
  actions,
  legend,
  loading = false,
  error,
  empty = false,
  emptyMessage = "Try a wider date range, or check back once usage has been recorded.",
  emptyContent,
  className,
  bodyClassName,
  minHeight = 280,
}: ChartCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ transition: { duration: 0.2 } }}
      className={cn(
        "glass-card rounded-card-lg border border-border-subtle relative overflow-hidden",
        "transition-shadow duration-base hover:shadow-elevated",
        className,
      )}
    >
      {/* Top accent line */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-tx-primary">{title}</h3>
          {subtitle && <p className="text-xs text-tx-muted mt-0.5">{subtitle}</p>}
        </div>
        {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
      </div>

      {legend && (
        <div className="px-5 pb-3 flex items-center gap-4 flex-wrap">{legend}</div>
      )}

      {/* Body */}
      <div className={cn("px-2 pb-4", bodyClassName)} style={{ minHeight }}>
        {loading ? (
          <ChartSkeleton height={minHeight} />
        ) : error ? (
          <div className="flex items-center justify-center h-full text-tx-muted text-sm">
            <span className="text-danger mr-1">⚠</span> Failed to load chart data
          </div>
        ) : empty ? (
          emptyContent ? (
            <div className="flex items-center justify-center" style={{ height: minHeight }}>
              {emptyContent}
            </div>
          ) : (
            <ChartEmpty height={minHeight} message={emptyMessage} />
          )
        ) : (
          children
        )}
      </div>
    </motion.div>
  );
}
