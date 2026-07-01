import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn, formatCost, formatNumber } from "../lib/utils";

type GradientVariant = "teal" | "indigo" | "emerald" | "amber" | "blue" | "purple";

interface MetricCardProps {
  label: string;
  value: string | number;
  type?: "currency" | "number" | "raw";
  currency?: string;
  trendPct?: number | undefined;
  trendInverse?: boolean;
  subtitle?: string;
  icon?: React.ElementType;
  gradient?: GradientVariant;
  sparkline?: number[];
  loading?: boolean;
  compact?: boolean;
}

const GRADIENT_CLASSES: Record<GradientVariant, string> = {
  teal:    "metric-gradient-teal   border-brand/20",
  indigo:  "metric-gradient-indigo border-primary/20",
  emerald: "metric-gradient-emerald border-success/20",
  amber:   "metric-gradient-amber  border-warning/20",
  blue:    "metric-gradient-blue   border-info/20",
  purple:  "metric-gradient-purple border-[#A855F7]/20",
};

const ICON_BG: Record<GradientVariant, string> = {
  teal:    "bg-brand-subtle text-brand",
  indigo:  "bg-primary-subtle text-primary-light",
  emerald: "bg-success-dim text-success-light",
  amber:   "bg-warning-dim text-warning-light",
  blue:    "bg-info-dim text-info-light",
  purple:  "bg-[rgba(168,85,247,0.12)] text-[#C084FC]",
};

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 28;
  const step = w / (data.length - 1);

  const points = data
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");

  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.7"
      />
    </svg>
  );
}

export default function MetricCard({
  label,
  value,
  type = "raw",
  currency = "USD",
  trendPct,
  trendInverse = false,
  subtitle,
  icon: Icon,
  gradient = "indigo",
  sparkline,
  loading = false,
  compact = false,
}: MetricCardProps) {
  if (loading) {
    return (
      <div className="glass-card p-5 border">
        <div className="flex items-start justify-between mb-4">
          <div className="w-8 h-8 skeleton rounded-lg" />
          <div className="w-16 h-4 skeleton rounded" />
        </div>
        <div className="w-24 h-7 skeleton rounded mb-1" />
        <div className="w-32 h-3 skeleton rounded" />
      </div>
    );
  }

  const formattedValue =
    type === "currency"
      ? formatCost(String(value), currency, compact)
      : type === "number"
        ? formatNumber(Number(value), compact)
        : String(value);

  const trendDir = trendPct === undefined ? null : trendPct > 0.1 ? "up" : trendPct < -0.1 ? "down" : "flat";
  const isPositive = trendInverse ? trendDir === "down" : trendDir === "up";
  const trendClass = trendDir === null
    ? ""
    : isPositive
      ? "text-success"
      : trendDir === "flat"
        ? "text-tx-muted"
        : "text-danger";

  const SPARK_COLORS: Record<GradientVariant, string> = {
    teal:    "#28E0C2",
    indigo:  "#4F46E5",
    emerald: "#10B981",
    amber:   "#F59E0B",
    blue:    "#3B82F6",
    purple:  "#A855F7",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2, transition: { duration: 0.15 } }}
      className={cn(
        "glass-card p-5 border cursor-default",
        GRADIENT_CLASSES[gradient],
        "transition-shadow duration-200 hover:shadow-card-hover",
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        {Icon && (
          <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0", ICON_BG[gradient])}>
            <Icon size={15} />
          </div>
        )}
        <div className="flex-1 min-w-0 ml-2">
          <p className="text-xs text-tx-muted font-medium leading-tight truncate">{label}</p>
        </div>
        {trendPct !== undefined && trendDir !== null && (
          <div className={cn("flex items-center gap-0.5 text-xs font-semibold ml-2", trendClass)}>
            {trendDir === "up" ? (
              <TrendingUp size={12} />
            ) : trendDir === "down" ? (
              <TrendingDown size={12} />
            ) : (
              <Minus size={12} />
            )}
            <span>{Math.abs(trendPct).toFixed(1)}%</span>
          </div>
        )}
      </div>

      {/* Value */}
      <div className="mb-2">
        <p className="text-2xl font-bold text-tx-primary tracking-tight leading-none">
          {formattedValue}
        </p>
      </div>

      {/* Bottom row */}
      <div className="flex items-end justify-between">
        <p className="text-xs text-tx-muted leading-tight">{subtitle ?? "vs prev period"}</p>
        {sparkline && (
          <Sparkline data={sparkline} color={SPARK_COLORS[gradient]} />
        )}
      </div>
    </motion.div>
  );
}
