import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn, formatCost, formatNumber } from "../lib/utils";
import { useCountUp } from "../hooks/useCountUp";

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

const ICON_GLOW: Record<GradientVariant, string> = {
  teal:    "shadow-[0_0_16px_rgba(40,224,194,0.35)]",
  indigo:  "shadow-[0_0_16px_rgba(79,70,229,0.35)]",
  emerald: "shadow-[0_0_16px_rgba(16,185,129,0.3)]",
  amber:   "shadow-[0_0_16px_rgba(245,158,11,0.3)]",
  blue:    "shadow-[0_0_16px_rgba(59,130,246,0.3)]",
  purple:  "shadow-[0_0_16px_rgba(168,85,247,0.3)]",
};

const SPARK_COLORS: Record<GradientVariant, string> = {
  teal:    "#28E0C2",
  indigo:  "#4F46E5",
  emerald: "#10B981",
  amber:   "#F59E0B",
  blue:    "#3B82F6",
  purple:  "#A855F7",
};

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 28;
  const step = w / (data.length - 1);

  const points = data.map((v, i) => [i * step, h - ((v - min) / range) * h] as const);
  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
  const areaPath = `${linePath} L${w},${h} L0,${h} Z`;
  const gradId = `spark-${color.replace("#", "")}`;

  return (
    <svg width={w} height={h} className="overflow-visible">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} stroke="none" />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AnimatedValue({
  value,
  type,
  currency,
  compact,
}: {
  value: string | number;
  type: "currency" | "number" | "raw";
  currency: string;
  compact: boolean;
}) {
  const numeric = typeof value === "number" ? value : parseFloat(value);
  const animatable = type !== "raw" && Number.isFinite(numeric);
  const animated = useCountUp(animatable ? numeric : 0);

  if (!animatable) return <>{value}</>;

  return <>{type === "currency" ? formatCost(animated, currency, compact) : formatNumber(animated, compact)}</>;
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
      <div className="glass-card rounded-card-lg p-5 border">
        <div className="flex items-start justify-between mb-4">
          <div className="w-9 h-9 skeleton rounded-xl" />
          <div className="w-16 h-4 skeleton rounded" />
        </div>
        <div className="w-24 h-8 skeleton rounded mb-2" />
        <div className="w-32 h-3 skeleton rounded" />
      </div>
    );
  }

  const trendDir = trendPct === undefined ? null : trendPct > 0.1 ? "up" : trendPct < -0.1 ? "down" : "flat";
  const isPositive = trendInverse ? trendDir === "down" : trendDir === "up";
  const trendClass = trendDir === null
    ? ""
    : isPositive
      ? "text-success bg-success-dim"
      : trendDir === "flat"
        ? "text-tx-muted bg-app-muted"
        : "text-danger bg-danger-dim";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -3, transition: { duration: 0.2, ease: "easeOut" } }}
      className={cn(
        "group glass-card rounded-card-lg p-5 border cursor-default relative overflow-hidden",
        GRADIENT_CLASSES[gradient],
        "transition-shadow duration-base hover:shadow-elevated",
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-4">
        {Icon && (
          <div
            className={cn(
              "w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0",
              "transition-transform duration-base group-hover:scale-110",
              ICON_BG[gradient],
              ICON_GLOW[gradient],
            )}
          >
            <Icon size={16} />
          </div>
        )}
        <div className="flex-1 min-w-0 ml-2.5 pt-0.5">
          <p className="text-xs text-tx-muted font-medium leading-tight truncate">{label}</p>
        </div>
        {trendPct !== undefined && trendDir !== null && (
          <div className={cn("flex items-center gap-0.5 text-[11px] font-semibold ml-2 px-1.5 py-0.5 rounded-full flex-shrink-0", trendClass)}>
            {trendDir === "up" ? (
              <TrendingUp size={11} />
            ) : trendDir === "down" ? (
              <TrendingDown size={11} />
            ) : (
              <Minus size={11} />
            )}
            <span>{Math.abs(trendPct).toFixed(1)}%</span>
          </div>
        )}
      </div>

      {/* Value */}
      <div className="mb-2">
        <p className="text-[28px] font-bold text-tx-primary tracking-tight leading-none tabular-nums">
          <AnimatedValue value={value} type={type} currency={currency} compact={compact} />
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
