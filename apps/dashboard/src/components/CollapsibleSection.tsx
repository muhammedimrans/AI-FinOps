import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../utils";

interface CollapsibleSectionProps {
  title: string;
  icon?: React.ElementType;
  defaultOpen?: boolean;
  summary?: ReactNode;
  children: ReactNode;
}

/** Compact, collapsible sections for the right-side configuration panel
 * (Provider & Model / Advanced Parameters / System Prompt) — redesign goal
 * #5. A generic building block, not a new "collapsible" abstraction per
 * section — reused by all three, and lightweight enough to reuse anywhere
 * else in this app that wants a collapsible group later. */
export default function CollapsibleSection({
  title,
  icon: Icon,
  defaultOpen = true,
  summary,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = `collapsible-${title.replace(/\s+/g, "-").toLowerCase()}`;

  return (
    <div className="glass-card rounded-card-lg border border-border-subtle overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-app-hover transition-colors"
      >
        <span className="flex items-center gap-2 min-w-0">
          {Icon && <Icon size={14} className="text-tx-muted flex-shrink-0" />}
          <span className="text-sm font-semibold text-tx-primary truncate">{title}</span>
        </span>
        <span className="flex items-center gap-2 flex-shrink-0">
          {!open && summary && <span className="text-[11px] text-tx-muted truncate max-w-[140px]">{summary}</span>}
          <ChevronDown
            size={14}
            className={cn("text-tx-muted transition-transform duration-base", open && "rotate-180")}
          />
        </span>
      </button>
      {open && (
        <div id={bodyId} className="px-4 pb-4 pt-1 border-t border-border-subtle">
          {children}
        </div>
      )}
    </div>
  );
}
