import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Moon, Sun, Zap } from "lucide-react";
import { cn } from "../lib/utils";
import { THEMES, useThemeStore, type ThemeId } from "../stores/theme";

const DROPDOWN_TRANSITION = { duration: 0.15, ease: "easeOut" as const };

const THEME_ICONS: Record<ThemeId, typeof Sun> = {
  "neon-cyber": Zap,
  "professional-light": Sun,
  "professional-dark": Moon,
};

/** Top-nav theme switcher — click-outside/Escape-to-close dropdown, matches the header's other menus. */
export default function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const ActiveIcon = THEME_ICONS[theme];

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", onClickOutside);
      document.addEventListener("keydown", onKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Change theme"
        className={cn("btn-ghost h-8 w-8 p-0 justify-center", open && "text-brand bg-app-hover")}
      >
        <ActiveIcon size={16} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            aria-label="Theme"
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={DROPDOWN_TRANSITION}
            className="absolute right-0 top-full mt-2 w-56 glass-card rounded-xl shadow-elevated z-50 py-1.5 origin-top-right"
          >
            {THEMES.map((t) => {
              const Icon = THEME_ICONS[t.id];
              const active = t.id === theme;
              return (
                <button
                  key={t.id}
                  role="menuitemradio"
                  aria-checked={active}
                  onClick={() => { setTheme(t.id); setOpen(false); }}
                  className={cn(
                    "w-full flex items-center gap-2.5 text-left px-3 py-2 text-xs transition-colors rounded-md mx-1 w-[calc(100%-8px)]",
                    active ? "text-brand bg-brand-subtle font-medium" : "text-tx-secondary hover:text-tx-primary hover:bg-app-hover",
                  )}
                >
                  <Icon size={14} className="flex-shrink-0" />
                  <span className="flex-1 min-w-0">
                    <span className="block truncate">{t.label}</span>
                    <span className="block text-[10px] text-tx-muted truncate">{t.description}</span>
                  </span>
                  {active && <Check size={13} className="flex-shrink-0" />}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
