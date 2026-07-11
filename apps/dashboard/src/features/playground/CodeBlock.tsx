import { useState } from "react";
import { Check, Copy } from "lucide-react";

// EP-25.4.1 — syntax "highlighting" for LLM-response code blocks without a
// new dependency (this app has none for markdown/highlighting today — see
// CLAUDE.md's EP-25.4 note). A small keyword/string/comment/number
// tokenizer covering the languages an LLM response realistically uses
// (Python, JS/TS, JSON, bash, SQL, etc.) — not a full grammar, but real
// token-level color, not just monospace text. Split into its own file
// (rather than living alongside markdown.tsx's plain renderMarkdown()
// function) so this file exports only a component — mixing a component
// export with a plain-function export in one file breaks React Fast
// Refresh, which eslint-plugin-react-refresh's `only-export-components`
// rule (already enforced repo-wide) correctly flags.

const KEYWORDS = new Set([
  "function", "const", "let", "var", "return", "if", "else", "for", "while",
  "class", "import", "export", "from", "async", "await", "try", "catch",
  "def", "elif", "except", "finally", "with", "as", "lambda", "yield",
  "public", "private", "static", "void", "new", "this", "self", "None",
  "True", "False", "null", "undefined", "interface", "type", "extends",
  "implements", "switch", "case", "break", "continue", "throw", "in", "of",
  "select", "from", "where", "insert", "update", "delete", "create", "table",
]);

interface Token {
  text: string;
  kind: "keyword" | "string" | "comment" | "number" | "plain";
}

function tokenizeLine(line: string): Token[] {
  const tokens: Token[] = [];
  const pattern = /(\/\/.*$|#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_][A-Za-z0-9_]*\b)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(line)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ text: line.slice(lastIndex, match.index), kind: "plain" });
    }
    if (match[1]) tokens.push({ text: match[1], kind: "comment" });
    else if (match[2]) tokens.push({ text: match[2], kind: "string" });
    else if (match[3]) tokens.push({ text: match[3], kind: "number" });
    else if (match[4]) {
      tokens.push({ text: match[4], kind: KEYWORDS.has(match[4]) ? "keyword" : "plain" });
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < line.length) tokens.push({ text: line.slice(lastIndex), kind: "plain" });
  return tokens;
}

const TOKEN_CLASS: Record<Token["kind"], string> = {
  keyword: "text-brand font-medium",
  string: "text-success",
  comment: "text-tx-muted italic",
  number: "text-warning",
  plain: "text-tx-primary",
};

function HighlightedCode({ code }: { code: string }) {
  const lines = code.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <div key={i}>
          {line.length === 0 ? (
            " "
          ) : (
            tokenizeLine(line).map((t, j) => (
              <span key={j} className={TOKEN_CLASS[t.kind]}>
                {t.text}
              </span>
            ))
          )}
        </div>
      ))}
    </>
  );
}

export default function CodeBlock({ code, language }: { code: string; language?: string | undefined }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="my-2 overflow-hidden rounded-lg border border-border-subtle bg-app-bg">
      <div className="flex items-center justify-between border-b border-border-subtle bg-app-muted px-3 py-1.5">
        <span className="text-[10px] font-mono uppercase tracking-wide text-tx-muted">
          {language || "text"}
        </span>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="inline-flex items-center gap-1 text-[10px] text-tx-muted hover:text-tx-primary transition-colors"
          aria-label="Copy code"
        >
          {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs font-mono leading-relaxed">
        <code>
          <HighlightedCode code={code} />
        </code>
      </pre>
    </div>
  );
}
