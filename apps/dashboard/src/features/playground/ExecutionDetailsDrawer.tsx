import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand } from "../../lib/providerCatalog";
import { formatCost, formatLatency } from "./format";
import PipelineTimeline from "./PipelineTimeline";
import type { ConversationTurn } from "./types";

// EP-25.4.3 Part 6 — a slide-out drawer of everything real that's known
// about one execution. Every field is either (a) real data the API
// returned, (b) real data the frontend itself sent as the request body
// (so "Request Payload" is the literal JSON this client posted — not a
// fabrication, since we're the ones who sent it), or (c) explicitly
// disclosed as not exposed by Costorah's API rather than invented — see
// each row's own comment below. No backend file changed to add this; every
// value already existed in PlaygroundExecutionRecord or was already known
// client-side before the request was sent.
function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-border-subtle/60 last:border-b-0">
      <span className="text-[11px] text-tx-muted flex-shrink-0">{label}</span>
      <span className={`text-[11px] text-tx-primary text-right break-all ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="rounded-lg bg-app-bg border border-border-subtle p-2.5 text-[10px] font-mono text-tx-primary overflow-x-auto max-h-56 overflow-y-auto">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export default function ExecutionDetailsDrawer({
  turn,
  open,
  onClose,
}: {
  turn: ConversationTurn | null;
  open: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);

  if (!turn) return null;
  const execution = turn.execution;
  const brand = getProviderBrand(turn.providerType);

  const requestPayload = {
    provider_connection_id: turn.connectionId,
    model_id: turn.model,
    system_prompt: turn.systemPrompt || undefined,
    user_prompt: turn.userPrompt,
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[160] flex justify-end">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.div
            ref={ref}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label="Execution details"
            initial={{ x: 32, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 32, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="relative w-full max-w-md h-full glass-panel shadow-elevated overflow-y-auto p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-tx-primary">Execution details</h2>
              <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 text-tx-muted hover:text-tx-primary">
                <X size={16} />
              </button>
            </div>

            <div className="flex items-center gap-2 mb-4">
              <ProviderLogo providerId={turn.providerType} size="sm" />
              <div>
                <p className="text-sm font-semibold text-tx-primary">{brand.displayName}</p>
                <p className="text-[11px] font-mono text-tx-muted">{turn.model}</p>
              </div>
            </div>

            <section className="mb-4">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tx-muted mb-1.5">Overview</p>
              <Row label="Execution ID" value={execution?.id ?? "—"} mono />
              <Row label="Provider connection" value={turn.connectionId} mono />
              {/* Endpoint is a static fact of this app's own API surface (EP-25.4), not returned by
                  the API response itself — real, just known ahead of time rather than echoed back. */}
              <Row label="Endpoint" value="POST /playground/execute" mono />
              {/* FastAPI's router declares 201 for a successful call (verified by reading
                  app/api/v1/playground.py — read-only, unmodified); the client's generic HTTP
                  helper doesn't surface the status code to callers on success, so this is stated
                  from the known route declaration, not measured per-request. */}
              <Row label="HTTP status" value={execution ? "201 Created" : turn.error ? "Request failed (see error)" : "Pending"} mono />
              <Row label="Latency" value={formatLatency(execution?.latency_ms ?? null)} mono />
              <Row
                label="Retry count"
                value={<span className="text-tx-muted italic">Not exposed by the API — HTTP-layer retries happen server-side (EP-06/EP-07) but aren't counted per request</span>}
              />
            </section>

            <section className="mb-4">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tx-muted mb-1.5">Token usage &amp; cost</p>
              <Row label="Prompt tokens" value={execution?.prompt_tokens ?? "—"} mono />
              <Row label="Completion tokens" value={execution?.completion_tokens ?? "—"} mono />
              <Row label="Total tokens" value={execution?.total_tokens ?? "—"} mono />
              <Row label="Estimated cost" value={execution ? formatCost(execution.estimated_cost, execution.currency) : "—"} mono />
            </section>

            <section className="mb-4">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tx-muted mb-1.5">Request payload</p>
              <p className="text-[10px] text-tx-muted mb-1">The exact JSON this browser sent to Costorah's API.</p>
              <JsonBlock data={requestPayload} />
            </section>

            <section className="mb-4">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tx-muted mb-1.5">Response payload</p>
              <p className="text-[10px] text-tx-muted mb-1">
                {execution
                  ? "The execution record Costorah's API returned. Costorah never stores or returns the raw provider request/response body."
                  : "No response yet."}
              </p>
              {execution ? <JsonBlock data={execution} /> : null}
            </section>

            <section className="mb-4">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tx-muted mb-1.5">Headers (safe only)</p>
              <p className="text-[10px] text-tx-muted mb-1">
                Only the headers this browser sent to Costorah's own API — never the provider's own request/response headers, which Costorah doesn't return to the client.
              </p>
              <JsonBlock data={{ Accept: "application/json", "Content-Type": "application/json", Authorization: "Bearer •••• (redacted)" }} />
            </section>

            <section>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tx-muted mb-2">Timeline</p>
              <PipelineTimeline turn={turn} />
            </section>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
