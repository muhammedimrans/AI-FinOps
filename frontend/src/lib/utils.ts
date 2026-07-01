import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ── Number formatting ─────────────────────────────────────────────────────────

export function formatCost(
  value: string | number,
  currency = "USD",
  compact = false,
): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";

  const formatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: compact && num >= 1000 ? 0 : 2,
    maximumFractionDigits: num >= 1000 ? 2 : 6,
    notation: compact ? "compact" : "standard",
  });
  return formatter.format(num);
}

export function formatNumber(value: number, compact = false): string {
  if (isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value);
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}

export function formatTokens(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toString();
}

// ── Date utilities ────────────────────────────────────────────────────────────

export function toISODate(date: Date): string {
  return date.toISOString().split("T")[0]!;
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

export function subtractDays(date: Date, days: number): Date {
  return addDays(date, -days);
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatDateFull(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatDateTime(isoStr: string): string {
  const d = new Date(isoStr);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getDaysAgo(days: number): string {
  return toISODate(subtractDays(new Date(), days));
}

export function getToday(): string {
  return toISODate(new Date());
}

// ── Trend helpers ─────────────────────────────────────────────────────────────

export function trendColor(pct: number): string {
  if (pct > 0) return "text-danger";
  if (pct < 0) return "text-success";
  return "text-tx-muted";
}

export function trendColorInverse(pct: number): string {
  if (pct > 0) return "text-success";
  if (pct < 0) return "text-danger";
  return "text-tx-muted";
}

export function trendIcon(pct: number): "up" | "down" | "flat" {
  if (pct > 0.1) return "up";
  if (pct < -0.1) return "down";
  return "flat";
}

// ── Misc ──────────────────────────────────────────────────────────────────────

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function slugify(str: string): string {
  return str.toLowerCase().replace(/\s+/g, "-");
}

export function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function truncate(str: string, len: number): string {
  return str.length > len ? `${str.slice(0, len)}…` : str;
}

export function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

export function providerDisplayName(provider: string): string {
  const map: Record<string, string> = {
    openai: "OpenAI",
    anthropic: "Anthropic",
    google: "Google",
    azure: "Azure",
    bedrock: "AWS Bedrock",
    cohere: "Cohere",
  };
  return map[provider.toLowerCase()] ?? capitalize(provider);
}

export function modelDisplayName(modelId: string): string {
  const map: Record<string, string> = {
    "gpt-4o": "GPT-4o",
    "gpt-4-turbo": "GPT-4 Turbo",
    "gpt-3.5-turbo": "GPT-3.5 Turbo",
    "claude-3-5-sonnet": "Claude 3.5 Sonnet",
    "claude-3-opus": "Claude 3 Opus",
    "claude-3-haiku": "Claude 3 Haiku",
    "gemini-pro": "Gemini Pro",
    "gemini-ultra": "Gemini Ultra",
    "azure-gpt-4": "Azure GPT-4",
    "azure-gpt-35": "Azure GPT-3.5",
  };
  return map[modelId] ?? modelId;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
