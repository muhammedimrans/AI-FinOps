import { CheckCircle2, XCircle } from "lucide-react";
import { formatNumber } from "../../utils";
import { formatCost, formatExecutionTime, formatLatency } from "./format";
import type { PlaygroundExecutionRecord } from "../../services/api";

// EP-25.4.1 redesign goal #7 — a real statistics panel after every
// execution. Every value is read directly off the PlaygroundExecutionRecord
// the backend already returns (EP-25.4) — no client-side estimation here.
export default function StatsPanel({ execution }: { execution: PlaygroundExecutionRecord }) {
  const stats: { label: string; value: string }[] = [
    { label: "Input tokens", value: formatNumber(execution.prompt_tokens) },
    { label: "Output tokens", value: formatNumber(execution.completion_tokens) },
    { label: "Total tokens", value: formatNumber(execution.total_tokens) },
    { label: "Estimated cost", value: formatCost(execution.estimated_cost, execution.currency) },
    { label: "Latency", value: formatLatency(execution.latency_ms) },
    { label: "Execution time", value: formatExecutionTime(execution.latency_ms) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 rounded-lg bg-app-muted p-3">
      {stats.map((s) => (
        <div key={s.label}>
          <p className="text-[10px] text-tx-muted">{s.label}</p>
          <p className="text-xs font-mono text-tx-primary">{s.value}</p>
        </div>
      ))}
      <div>
        <p className="text-[10px] text-tx-muted">Status</p>
        <p className={`text-xs font-medium flex items-center gap-1 ${execution.status === "succeeded" ? "text-success" : "text-danger"}`}>
          {execution.status === "succeeded" ? (
            <CheckCircle2 size={12} />
          ) : (
            <XCircle size={12} />
          )}
          {execution.status === "succeeded" ? "Succeeded" : "Failed"}
        </p>
      </div>
    </div>
  );
}
