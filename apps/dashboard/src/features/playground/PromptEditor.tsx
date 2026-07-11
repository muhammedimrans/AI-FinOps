import { useEffect, useRef } from "react";
import { Paperclip, X } from "lucide-react";

// EP-25.4.3 Part 4 — a professional prompt editor: auto-growing textarea,
// Ctrl+Enter to send (Enter alone inserts a newline — this app previously
// sent on plain Enter, EP-25.4.1; switched to the Ctrl/Cmd+Enter
// convention every reference product in this EP's brief actually uses),
// a live character counter, a rough token estimate, a Clear button, a
// slash-command hint (future-ready — no commands are implemented yet, so
// this is disclosed as a hint, not a working feature), and an Attach File
// button that is honestly disabled with "Coming soon" rather than a silent
// no-op.
//
// Token estimate: `Math.ceil(chars / 4)` — the same rough "~4 characters
// per token" heuristic every major provider's own docs use for ballpark
// estimates; disclosed as an estimate (title attribute + label), never
// presented as the real, provider-computed token count (that only exists
// once a request actually completes and the API returns real
// prompt_tokens/completion_tokens).
export default function PromptEditor({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Message the Playground…",
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
  }, [value]);

  const charCount = value.length;
  const estimatedTokens = value.trim() ? Math.ceil(value.length / 4) : 0;
  const sizeBytes = new Blob([value]).size;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative rounded-xl border border-border-subtle bg-app-bg focus-within:border-brand transition-colors">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              onSubmit();
            }
            if (e.key === "/" && value.length === 0) {
              // Slash-command hook point — no commands implemented yet
              // (Part 4's "future ready" requirement). Intentionally a
              // no-op beyond letting "/" type normally.
            }
          }}
          placeholder={placeholder}
          rows={1}
          aria-label="Message"
          disabled={disabled}
          className="w-full resize-none bg-transparent px-3.5 pt-3 pb-1 text-sm text-tx-primary outline-none placeholder:text-tx-muted disabled:opacity-60 max-h-80"
        />
        <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              title="Attach file — coming soon"
              className="inline-flex items-center gap-1 text-[10px] text-tx-muted opacity-50 cursor-not-allowed"
            >
              <Paperclip size={11} /> Attach
              <span className="badge bg-app-muted text-tx-muted text-[9px] ml-0.5">Coming soon</span>
            </button>
            {value.length > 0 && (
              <button
                type="button"
                onClick={() => onChange("")}
                title="Clear"
                className="inline-flex items-center gap-1 text-[10px] text-tx-muted hover:text-tx-primary"
              >
                <X size={11} /> Clear
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-tx-muted" title="Rough estimate — the real token count comes back with the response.">
            <span>{charCount.toLocaleString()} chars</span>
            <span>·</span>
            <span>~{estimatedTokens.toLocaleString()} tok (est.)</span>
            <span>·</span>
            <span>{sizeBytes.toLocaleString()} B</span>
          </div>
        </div>
      </div>
      <p className="text-[10px] text-tx-muted px-1">
        <kbd className="rounded border border-border-subtle px-1 py-0.5 font-mono">Ctrl</kbd>+
        <kbd className="rounded border border-border-subtle px-1 py-0.5 font-mono">Enter</kbd> to send ·{" "}
        <kbd className="rounded border border-border-subtle px-1 py-0.5 font-mono">/</kbd> for commands (coming soon)
      </p>
    </div>
  );
}
