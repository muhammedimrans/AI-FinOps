import type { PlaygroundExecutionRecord } from "../../services/api";

export function formatCost(cost: string | null, currency: string): string {
  if (cost === null) return "—";
  const n = Number(cost);
  if (Number.isNaN(n)) return "—";
  return n < 0.01 ? `<$0.01 ${currency}` : `$${n.toFixed(4)} ${currency}`;
}

export function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  return `${Math.round(ms)}ms`;
}

export function formatExecutionTime(ms: number | null): string {
  if (ms === null) return "—";
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatRelativeDay(iso: string): "Today" | "Yesterday" | "Earlier" {
  const date = new Date(iso);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return "Earlier";
}

export function groupByRelativeDay<T extends { created_at: string }>(
  items: T[],
): { label: string; items: T[] }[] {
  const groups: Record<string, T[]> = { Today: [], Yesterday: [], Earlier: [] };
  for (const item of items) {
    groups[formatRelativeDay(item.created_at)]!.push(item);
  }
  return (["Today", "Yesterday", "Earlier"] as const)
    .map((label) => ({ label, items: groups[label]! }))
    .filter((g) => g.items.length > 0);
}

/** Real math over real, already-fetched data: estimates what THIS
 * execution's actual token counts would have cost against another model's
 * published pricing. Never used unless both the source execution's cost
 * and the target model's per-1k rates are real, known values — see
 * CostAnalysis.tsx for the "never fabricate" guard. */
export function estimateCostForModel(
  execution: PlaygroundExecutionRecord,
  inputCostPer1k: number,
  outputCostPer1k: number,
): number {
  return (
    (execution.prompt_tokens / 1000) * inputCostPer1k +
    (execution.completion_tokens / 1000) * outputCostPer1k
  );
}
