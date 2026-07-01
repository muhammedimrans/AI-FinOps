import { useRef, useState } from "react";
import { Check, Moon, Sun, Zap } from "lucide-react";
import { cn } from "../utils";
import { THEMES, useThemeStore, type ThemeId } from "../stores/theme";
import Popover from "./Popover";

const THEME_ICONS: Record<ThemeId, typeof Sun> = {
  "neon-cyber": Zap,
  "professional-light": Sun,
  "professional-dark": Moon,
};

/** Top-nav theme switcher — portaled dropdown, matches the header's other menus. */
export default function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  const ActiveIcon = THEME_ICONS[theme];

  return (
    <div className="relative">
      <button
        ref={ref}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Change theme"
        className={cn("btn-ghost h-8 w-8 p-0 justify-center", open && "text-brand bg-app-hover")}
      >
        <ActiveIcon size={16} />
      </button>
      <Popover
        anchorRef={ref}
        open={open}
        onClose={() => setOpen(false)}
        align="end"
        className="w-56 glass-card rounded-xl shadow-elevated z-[1000] py-1.5 origin-top-right"
      >
        <div role="menu" aria-label="Theme">
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
        </div>
      </Popover>
    </div>
  );
}
