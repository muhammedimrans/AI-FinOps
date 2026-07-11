import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Braces,
  Copy,
  Download,
  FileJson,
  ListTree,
  RotateCw,
  Share2,
  Sparkles,
  Trash2,
  User,
} from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { renderMarkdown } from "./markdown";
import StatsPanel from "./StatsPanel";
import CostAnalysis, { type ModelsForConnection } from "./CostAnalysis";
import ProviderHeaderChips from "./ProviderHeaderChips";
import type { PlaygroundConnectionOption, PlaygroundModelInfo } from "../../services/api";
import type { ConversationTurn } from "./types";

interface MessageBubbleProps {
  turn: ConversationTurn;
  allTurns: ConversationTurn[];
  modelsByConnection: Record<string, ModelsForConnection>;
  connection: PlaygroundConnectionOption | undefined;
  model: PlaygroundModelInfo | undefined;
  onCopy: (text: string) => void;
  onRetry: (turn: ConversationTurn) => void;
  onContinue: (turn: ConversationTurn) => void;
  onDownloadMarkdown: (turn: ConversationTurn) => void;
  onDelete: (turn: ConversationTurn) => void;
  onCostAnalysisOpen: () => void;
  onOpenDetails: (turn: ConversationTurn) => void;
}

function formatTime(iso: string | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** EP-25.4.3 Part 1 — simulates progressive rendering. Costorah's backend
 * has no streaming endpoint (PlaygroundService's own architecture is one
 * synchronous request/response, unchanged by this EP — see CLAUDE.md's
 * EP-25.4 section) — this hook animates the REAL, already-fully-arrived
 * response text into view character-by-character rather than displaying it
 * instantly, and only does so for a turn that was actually pending when
 * this component first mounted (i.e. a live send in this browser session).
 * A turn that's already complete when it mounts (switching conversations,
 * reopening one from history) renders its full text immediately — nothing
 * replays a "typing" animation for text the user has already seen. */
function useStreamReveal(fullText: string, isPending: boolean, hasArrived: boolean) {
  const [revealLength, setRevealLength] = useState(hasArrived ? fullText.length : 0);
  const wasPendingOnMount = useRef(isPending);
  const startedRef = useRef(false);

  useEffect(() => {
    if (!wasPendingOnMount.current) {
      setRevealLength(fullText.length);
      return undefined;
    }
    if (!hasArrived || startedRef.current) return undefined;
    startedRef.current = true;
    setRevealLength(0);
    const totalTicks = 28;
    const step = Math.max(1, Math.ceil(fullText.length / totalTicks));
    let current = 0;
    const interval = setInterval(() => {
      current += step;
      setRevealLength((prev) => Math.min(Math.max(prev, current), fullText.length));
      if (current >= fullText.length) clearInterval(interval);
    }, 18);
    return () => clearInterval(interval);
  }, [fullText, hasArrived]);

  return revealLength;
}

function useStageLabel(isPending: boolean): "thinking" | "generating" {
  const [thinkingDone, setThinkingDone] = useState(false);
  useEffect(() => {
    if (!isPending) {
      setThinkingDone(false);
      return undefined;
    }
    setThinkingDone(false);
    const t = setTimeout(() => setThinkingDone(true), 450);
    return () => clearTimeout(t);
  }, [isPending]);
  return isPending && !thinkingDone ? "thinking" : "generating";
}

export default function MessageBubble({
  turn,
  allTurns,
  modelsByConnection,
  connection,
  model,
  onCopy,
  onRetry,
  onContinue,
  onDownloadMarkdown,
  onDelete,
  onCostAnalysisOpen,
  onOpenDetails,
}: MessageBubbleProps) {
  const responseText = turn.execution?.response_text ?? "";
  const hasArrived = !!turn.execution && turn.execution.status === "succeeded";
  const revealLength = useStreamReveal(responseText, turn.isPending, hasArrived);
  const isRevealing = hasArrived && revealLength < responseText.length;
  const stage = useStageLabel(turn.isPending);
  const [showRawJson, setShowRawJson] = useState(false);

  function downloadJson() {
    if (!turn.execution) return;
    const blob = new Blob([JSON.stringify(turn.execution, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `costorah-playground-${turn.execution.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function share() {
    if (!turn.execution?.response_text) return;
    const text = `Prompt: ${turn.userPrompt}\n\nResponse (${turn.providerType}/${turn.model}):\n${turn.execution.response_text}\n\n— Shared from Costorah AI Playground`;
    if (navigator.share) {
      try {
        await navigator.share({ text });
        return;
      } catch {
        // User cancelled or Web Share failed — fall through to clipboard.
      }
    }
    onCopy(text);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="flex flex-col gap-2"
    >
      {/* User bubble — right aligned */}
      <div className="flex items-start gap-2 justify-end">
        <div className="flex flex-col items-end max-w-[85%]">
          <div className="group relative rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2.5 text-sm text-white whitespace-pre-wrap shadow-card">
            {turn.isContinuation && (
              <p className="mb-1 text-[10px] uppercase tracking-wide text-white/70">Continue</p>
            )}
            {turn.userPrompt}
          </div>
          <span className="text-[10px] text-tx-muted mt-0.5 mr-0.5">{formatTime(turn.execution?.created_at)}</span>
        </div>
        <div className="flex flex-col items-center gap-1 pt-1 flex-shrink-0">
          <div className="w-7 h-7 rounded-full bg-app-muted flex items-center justify-center">
            <User size={13} className="text-tx-muted" />
          </div>
          <button type="button" onClick={() => onCopy(turn.userPrompt)} className="p-1 text-tx-muted hover:text-tx-primary" aria-label="Copy prompt">
            <Copy size={12} />
          </button>
        </div>
      </div>

      {/* Assistant response — left aligned */}
      <div className="flex items-start gap-2">
        <div className="pt-1 flex-shrink-0">
          <ProviderLogo providerId={turn.providerType} size="sm" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="rounded-2xl rounded-tl-sm border border-border-subtle bg-app-card px-3.5 py-2.5">
            {turn.isPending ? (
              <div className="flex items-center gap-2 text-xs text-tx-muted py-1">
                <span className="flex gap-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-brand animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-brand animate-bounce" />
                </span>
                {stage === "thinking" ? "Thinking…" : "Generating response…"}
              </div>
            ) : turn.error ? (
              <FailureBlock message={turn.error} onRetry={() => onRetry(turn)} />
            ) : turn.execution?.status === "failed" ? (
              <FailureBlock message={turn.execution.error_message ?? "The provider returned an error."} onRetry={() => onRetry(turn)} />
            ) : turn.execution ? (
              <div className="flex flex-col gap-2.5">
                <ProviderHeaderChips execution={turn.execution} connection={connection} model={model} />

                <div className="text-sm text-tx-primary [&_pre]:my-0">
                  {isRevealing ? (
                    <>
                      <span className="whitespace-pre-wrap">{responseText.slice(0, revealLength)}</span>
                      <span className="inline-block w-1.5 h-3.5 bg-brand/70 ml-0.5 align-middle animate-pulse" aria-hidden="true" />
                    </>
                  ) : (
                    renderMarkdown(responseText)
                  )}
                </div>

                {!isRevealing && (
                  <>
                    <div className="flex flex-wrap items-center gap-1 border-t border-border-subtle pt-2">
                      <ActionButton icon={Copy} label="Copy" onClick={() => onCopy(responseText)} />
                      <ActionButton icon={RotateCw} label="Retry" onClick={() => onRetry(turn)} />
                      <ActionButton
                        icon={Sparkles}
                        label="Continue"
                        onClick={() => onContinue(turn)}
                        title="Sends a new request asking the model to continue — Playground requests are independent, so only that instruction is sent, not full conversation history."
                      />
                      <ActionButton icon={Download} label="Download Markdown" onClick={() => onDownloadMarkdown(turn)} />
                      <ActionButton icon={FileJson} label="Download JSON" onClick={downloadJson} />
                      <ActionButton icon={Share2} label="Share" onClick={() => void share()} />
                      <ActionButton icon={Braces} label="View Raw JSON" onClick={() => setShowRawJson((v) => !v)} />
                      <ActionButton icon={ListTree} label="View Execution Details" onClick={() => onOpenDetails(turn)} />
                      <ActionButton icon={Trash2} label="Delete" onClick={() => onDelete(turn)} danger />
                    </div>

                    {showRawJson && (
                      <pre className="rounded-lg bg-app-bg border border-border-subtle p-2.5 text-[10px] font-mono text-tx-primary overflow-x-auto max-h-56 overflow-y-auto">
                        {JSON.stringify(turn.execution, null, 2)}
                      </pre>
                    )}

                    <StatsPanel execution={turn.execution} />
                    <CostAnalysisToggle turn={turn} allTurns={allTurns} modelsByConnection={modelsByConnection} onOpen={onCostAnalysisOpen} />
                  </>
                )}
              </div>
            ) : null}
          </div>
          {!turn.isPending && turn.execution && (
            <span className="text-[10px] text-tx-muted mt-0.5 ml-0.5 block">{formatTime(turn.execution.created_at)}</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function FailureBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-danger">{message}</p>
      <button type="button" onClick={onRetry} className="btn-outline h-7 px-2 text-[11px] inline-flex items-center gap-1 self-start">
        <RotateCw size={11} /> Retry
      </button>
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  onClick,
  danger,
  title,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  danger?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title ?? label}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] transition-colors ${
        danger ? "text-tx-muted hover:text-danger hover:bg-danger-dim" : "text-tx-muted hover:text-tx-primary hover:bg-app-hover"
      }`}
    >
      <Icon size={11} />
      {label}
    </button>
  );
}

function CostAnalysisToggle({
  turn,
  allTurns,
  modelsByConnection,
  onOpen,
}: {
  turn: ConversationTurn;
  allTurns: ConversationTurn[];
  modelsByConnection: Record<string, ModelsForConnection>;
  onOpen: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!turn.execution || turn.execution.status !== "succeeded") return null;
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) onOpen();
        }}
        aria-expanded={open}
        className="text-[11px] font-medium text-brand hover:text-brand-hover inline-flex items-center gap-1"
      >
        <Sparkles size={11} /> {open ? "Hide cost analysis" : "Cost Analysis"}
      </button>
      {open && (
        <div className="mt-2">
          <CostAnalysis execution={turn.execution} modelsByConnection={modelsByConnection} turns={allTurns} />
        </div>
      )}
    </div>
  );
}
