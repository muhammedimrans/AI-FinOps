import { Check, Loader2, X } from "lucide-react";
import { cn } from "../../utils";
import type { ConversationTurn } from "./types";

type StageState = "done" | "active" | "pending" | "failed" | "skipped";

// EP-25.4.3 Part 7 — a pipeline visualization of what PlaygroundService
// actually does (CLAUDE.md's EP-25.4 architecture diagram, unchanged by
// this EP): decrypt credential -> build provider config -> call the
// provider -> write UsageEvent/UsageCostRecord -> evaluate budgets. This
// component does NOT have per-stage timestamps (PlaygroundExecutionRecord
// exposes none, and this EP does not add backend instrumentation to
// produce them) — every stage before "Response Received" is inferred from
// the turn's own pending/succeeded/failed state, and every stage from
// "Usage Recorded" onward is marked done-or-skipped based on one real,
// already-known fact: EP-25.4's own service only writes usage and
// evaluates budgets on a SUCCESSFUL execution (a failed request never
// reaches that code, CLAUDE.md's own "no usage on failure" contract) — so
// marking them "skipped" for a failed turn is accurate, not guessed.
const STAGES = [
  "Request Created",
  "Sent to Provider",
  "Provider Processing",
  "Response Received",
  "Usage Recorded",
  "Dashboard Updated",
  "Budget Evaluation",
  "Completed",
] as const;

function stagesFor(turn: ConversationTurn): StageState[] {
  if (turn.isPending) {
    return ["done", "done", "active", "pending", "pending", "pending", "pending", "pending"];
  }
  if (turn.error || turn.execution?.status === "failed") {
    return ["done", "done", "done", "failed", "skipped", "skipped", "skipped", "failed"];
  }
  if (turn.execution?.status === "succeeded") {
    return ["done", "done", "done", "done", "done", "done", "done", "done"];
  }
  return STAGES.map(() => "pending");
}

const DOT_CLASS: Record<StageState, string> = {
  done: "bg-success text-white",
  active: "bg-warning text-white animate-pulse",
  pending: "bg-app-muted text-tx-muted",
  failed: "bg-danger text-white",
  skipped: "bg-app-muted text-tx-disabled",
};

export default function PipelineTimeline({ turn }: { turn: ConversationTurn }) {
  const states = stagesFor(turn);
  return (
    <div className="flex flex-col gap-0">
      {STAGES.map((label, i) => {
        const state = states[i]!;
        const isLast = i === STAGES.length - 1;
        return (
          <div key={label} className="flex items-start gap-2.5">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0",
                  DOT_CLASS[state],
                )}
              >
                {state === "done" && <Check size={11} />}
                {state === "active" && <Loader2 size={11} className="animate-spin" />}
                {state === "failed" && <X size={11} />}
              </span>
              {!isLast && <span className={cn("w-px flex-1 min-h-[14px]", state === "pending" || state === "skipped" ? "bg-border-subtle" : "bg-success/40")} />}
            </div>
            <p
              className={cn(
                "text-[11px] pb-3",
                state === "done" ? "text-tx-primary" : state === "failed" ? "text-danger" : "text-tx-muted",
              )}
            >
              {label}
              {state === "skipped" && <span className="ml-1 text-tx-disabled">(skipped)</span>}
            </p>
          </div>
        );
      })}
    </div>
  );
}
