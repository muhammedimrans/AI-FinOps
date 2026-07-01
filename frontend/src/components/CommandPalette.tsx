import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Search, CornerDownLeft, ArrowUp, ArrowDown } from "lucide-react";
import { NAV_ITEMS } from "../lib/navigation";
import { useUIStore } from "../stores/ui";
import { cn } from "../utils";

/**
 * Global quick-jump palette — Cmd+K / Ctrl+K to open (wired in AppLayout).
 * Filters the shared NAV_ITEMS list by label/group/keywords, arrow keys to
 * move selection, Enter to navigate, Escape or backdrop click to dismiss.
 */
export default function CommandPalette() {
  const { commandOpen, setCommandOpen } = useUIStore();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAV_ITEMS;
    return NAV_ITEMS.filter((item) =>
      `${item.label} ${item.group} ${item.keywords ?? ""}`.toLowerCase().includes(q),
    );
  }, [query]);

  useEffect(() => {
    if (commandOpen) {
      setQuery("");
      setActiveIndex(0);
      // Focus after the open animation frame so the input actually exists.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [commandOpen]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  function close() {
    setCommandOpen(false);
  }

  function go(item: (typeof NAV_ITEMS)[number]) {
    navigate(item.to);
    close();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = results[activeIndex];
      if (item) go(item);
    }
  }

  return (
    <AnimatePresence>
      {commandOpen && (
        <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={close}
            aria-hidden="true"
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Quick navigation"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="relative w-full max-w-lg glass-card border border-border-subtle shadow-card-hover overflow-hidden"
            onKeyDown={handleKeyDown}
          >
            <div className="flex items-center gap-3 px-4 h-12 border-b border-border-subtle">
              <Search size={16} className="text-tx-muted flex-shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search pages…"
                className="flex-1 bg-transparent text-sm text-tx-primary placeholder:text-tx-muted focus:outline-none"
              />
              <kbd className="hidden sm:inline-flex items-center px-1.5 h-5 rounded border border-border-subtle text-[10px] text-tx-muted">
                Esc
              </kbd>
            </div>

            <div className="max-h-80 overflow-y-auto py-1.5">
              {results.length === 0 && (
                <p className="px-4 py-6 text-center text-sm text-tx-muted">
                  No pages match &ldquo;{query}&rdquo;.
                </p>
              )}
              {results.map((item, i) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.to}
                    onClick={() => go(item)}
                    onMouseEnter={() => setActiveIndex(i)}
                    className={cn(
                      "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors duration-fast",
                      i === activeIndex ? "bg-brand-subtle text-tx-primary" : "text-tx-secondary",
                    )}
                  >
                    <Icon size={15} className={cn("flex-shrink-0", i === activeIndex && "text-brand")} />
                    <span className="text-sm flex-1 truncate">{item.label}</span>
                    <span className="text-[10px] text-tx-muted uppercase tracking-wide">{item.group}</span>
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-4 px-4 h-9 border-t border-border-subtle text-[10px] text-tx-muted">
              <span className="flex items-center gap-1">
                <ArrowUp size={11} /><ArrowDown size={11} /> Navigate
              </span>
              <span className="flex items-center gap-1">
                <CornerDownLeft size={11} /> Select
              </span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
