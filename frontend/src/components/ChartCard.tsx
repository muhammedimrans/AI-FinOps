import { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "../lib/utils";

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
  legend?: ReactNode;
  loading?: boolean;
  error?: string | null;
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

export default function ChartCard({
  title,
  subtitle,
  children,
  actions,
  legend,
  loading = false,
  error,
  className,
  bodyClassName,
  minHeight = 280,
}: ChartCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("glass-card border border-border-subtle", className)}
    >
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
        ) : (
          children
        )}
      </div>
    </motion.div>
  );
}
