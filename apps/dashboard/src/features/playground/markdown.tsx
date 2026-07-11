import { cn } from "../../utils";
import CodeBlock from "./CodeBlock";

// EP-25.4.1 — a richer, still dependency-free "markdown-lite" renderer.
// This app has no markdown library (EP-25.4's own CLAUDE.md note explains
// why: not worth a new dependency for one page) — this rewrite extends
// that same regex-based approach to cover the concrete redesign
// requirement ("render Markdown, tables, lists, and syntax-highlighted
// code blocks") without introducing one. Fenced code blocks render via
// CodeBlock.tsx (a separate file — see that file's own header comment for
// why); everything else here (tables, lists, headings, quotes, links,
// bold/italic/inline-code) stays in this file.

function renderInline(text: string, keyPrefix: string): React.ReactNode {
  const html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code class='px-1 py-0.5 rounded bg-app-muted font-mono text-[0.85em]'>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      "<a href='$2' target='_blank' rel='noreferrer' class='text-brand underline underline-offset-2 hover:text-brand-hover'>$1</a>",
    );
  return <span key={keyPrefix} dangerouslySetInnerHTML={{ __html: html }} />;
}

function renderTable(lines: string[], key: string): React.ReactNode {
  const rows = lines
    .filter((l) => !/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l))
    .map((l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  if (rows.length === 0) return null;
  const [header, ...body] = rows;
  return (
    <div key={key} className="my-2 overflow-x-auto rounded-lg border border-border-subtle">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-app-muted">
            {header!.map((cell, i) => (
              <th key={i} className="px-2.5 py-1.5 text-left font-semibold text-tx-secondary border-b border-border-subtle">
                {renderInline(cell, `h-${i}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 1 ? "bg-app-muted/40" : undefined}>
              {row.map((cell, ci) => (
                <td key={ci} className="px-2.5 py-1.5 text-tx-primary border-b border-border-subtle/60 last:border-b-0">
                  {renderInline(cell, `${ri}-${ci}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderTextBlock(block: string, keyPrefix: string): React.ReactNode[] {
  const lines = block.split("\n");
  const out: React.ReactNode[] = [];
  let i = 0;
  let paraBuffer: string[] = [];
  let listBuffer: { ordered: boolean; text: string }[] = [];

  function flushPara() {
    if (paraBuffer.length === 0) return;
    const text = paraBuffer.join(" ").trim();
    if (text) out.push(<p key={`${keyPrefix}-p-${out.length}`} className="mb-2 last:mb-0 leading-relaxed">{renderInline(text, `${keyPrefix}-pi-${out.length}`)}</p>);
    paraBuffer = [];
  }
  function flushList() {
    if (listBuffer.length === 0) return;
    const ordered = listBuffer[0]!.ordered;
    const Tag = ordered ? "ol" : "ul";
    out.push(
      <Tag key={`${keyPrefix}-l-${out.length}`} className={cn("mb-2 last:mb-0 pl-5 space-y-0.5", ordered ? "list-decimal" : "list-disc")}>
        {listBuffer.map((item, idx) => (
          <li key={idx} className="leading-relaxed">{renderInline(item.text, `${keyPrefix}-li-${idx}`)}</li>
        ))}
      </Tag>,
    );
    listBuffer = [];
  }

  while (i < lines.length) {
    const line = lines[i]!;
    const trimmed = line.trim();

    if (/^\|.*\|$/.test(trimmed)) {
      flushPara();
      flushList();
      const tableLines: string[] = [];
      while (i < lines.length && /^\|.*\|$/.test(lines[i]!.trim())) {
        tableLines.push(lines[i]!);
        i++;
      }
      out.push(renderTable(tableLines, `${keyPrefix}-t-${out.length}`));
      continue;
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flushPara();
      flushList();
      const level = heading[1]!.length;
      const HeadingTag = (`h${Math.min(level + 3, 6)}`) as keyof JSX.IntrinsicElements;
      const sizeClass = level === 1 ? "text-base font-semibold" : level === 2 ? "text-sm font-semibold" : "text-sm font-medium";
      out.push(<HeadingTag key={`${keyPrefix}-h-${out.length}`} className={cn(sizeClass, "mt-3 mb-1.5 first:mt-0 text-tx-primary")}>{renderInline(heading[2]!, `${keyPrefix}-hi-${out.length}`)}</HeadingTag>);
      i++;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushPara();
      flushList();
      out.push(<hr key={`${keyPrefix}-hr-${out.length}`} className="my-3 border-border-subtle" />);
      i++;
      continue;
    }

    const bulletMatch = /^[-*]\s+(.*)$/.exec(trimmed);
    const orderedMatch = /^\d+[.)]\s+(.*)$/.exec(trimmed);
    if (bulletMatch || orderedMatch) {
      flushPara();
      const isOrdered = !!orderedMatch;
      listBuffer.push({ ordered: isOrdered, text: (bulletMatch ?? orderedMatch)![1]! });
      i++;
      continue;
    }

    const quoteMatch = /^>\s?(.*)$/.exec(trimmed);
    if (quoteMatch) {
      flushPara();
      flushList();
      out.push(
        <blockquote key={`${keyPrefix}-q-${out.length}`} className="my-2 border-l-2 border-brand/50 pl-3 text-tx-secondary italic">
          {renderInline(quoteMatch[1]!, `${keyPrefix}-qi-${out.length}`)}
        </blockquote>,
      );
      i++;
      continue;
    }

    if (trimmed === "") {
      flushPara();
      flushList();
      i++;
      continue;
    }

    flushList();
    paraBuffer.push(line);
    i++;
  }
  flushPara();
  flushList();
  return out;
}

/** Renders an LLM response's markdown-ish text: fenced code blocks (with a
 * language label, copy button, and lightweight token highlighting), tables,
 * ordered/unordered lists, headings, blockquotes, horizontal rules, bold/
 * italic/inline-code/links, and paragraphs. */
export function renderMarkdown(text: string): React.ReactNode {
  const blocks = text.split(/```/);
  return blocks.map((block, i) => {
    if (i % 2 === 1) {
      const firstNewline = block.indexOf("\n");
      const maybeLang = firstNewline === -1 ? "" : block.slice(0, firstNewline).trim();
      const hasLang = maybeLang && !maybeLang.includes(" ") && maybeLang.length < 20;
      const code = hasLang ? block.slice(firstNewline + 1) : block;
      return <CodeBlock key={i} code={code.replace(/\n$/, "")} language={hasLang ? maybeLang : undefined} />;
    }
    return <span key={i}>{renderTextBlock(block, `b${i}`)}</span>;
  });
}
