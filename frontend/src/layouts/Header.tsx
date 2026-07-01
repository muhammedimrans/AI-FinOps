import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Bell,
  BellOff,
  Search,
  ChevronDown,
  Calendar,
  DollarSign,
  Menu,
} from "lucide-react";
import { cn, getDaysAgo, getToday, subtractDays, toISODate } from "../utils";
import { useUIStore } from "../stores/ui";
import ThemeSwitcher from "../components/ThemeSwitcher";
import Popover from "../components/Popover";
import type { Currency } from "../types/api";

const ROUTE_LABELS: Record<string, string> = {
  "/dashboard":              "Overview",
  "/dashboard/analytics":    "Cost Analytics",
  "/dashboard/providers":    "Providers",
  "/dashboard/models":       "Models",
  "/dashboard/projects":     "Projects",
  "/dashboard/organization": "Organization",
  "/users":                  "Users",
  "/rbac":                   "RBAC",
  "/api-keys":               "API Keys",
  "/connections":            "Provider Connections",
  "/audit-logs":             "Audit Logs",
  "/settings":               "Settings",
};

const DATE_PRESETS = [
  { label: "Today",     value: "today",     start: () => getToday(),                              end: () => getToday() },
  { label: "Yesterday", value: "yesterday", start: () => toISODate(subtractDays(new Date(), 1)),  end: () => toISODate(subtractDays(new Date(), 1)) },
  { label: "Last 7d",   value: "7d",        start: () => getDaysAgo(7),                            end: () => getToday() },
  { label: "Last 30d",  value: "30d",       start: () => getDaysAgo(30),                           end: () => getToday() },
  { label: "Last 90d",  value: "90d",       start: () => getDaysAgo(90),                           end: () => getToday() },
  { label: "This month",value: "month",     start: () => {
    const d = new Date(); d.setDate(1); return d.toISOString().split("T")[0]!;
  }, end: () => getToday() },
  { label: "Last year", value: "year",      start: () => getDaysAgo(365),                          end: () => getToday() },
];

const CURRENCIES: Currency[] = ["USD", "EUR", "GBP"];

interface HeaderProps {
  onMenuClick?: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();
  const { currency, setCurrency, datePreset, setDateRange, setCommandOpen } = useUIStore();
  const [dateOpen, setDateOpen] = useState(false);
  const [currencyOpen, setCurrencyOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const dateRef = useRef<HTMLDivElement>(null);
  const currencyRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  const pageLabel = ROUTE_LABELS[location.pathname] ?? "Dashboard";
  const breadcrumb = location.pathname.split("/").filter(Boolean);
  const currentPreset = DATE_PRESETS.find((p) => p.value === datePreset);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setCommandOpen]);

  function selectPreset(preset: (typeof DATE_PRESETS)[0]) {
    setDateRange(preset.value, preset.start(), preset.end());
    setDateOpen(false);
  }

  return (
    <header className="h-[60px] border-b border-border-subtle bg-app-bg/80 backdrop-blur-md flex items-center px-4 sm:px-6 gap-3 sm:gap-4 flex-shrink-0">
      {/* Mobile nav trigger */}
      <button
        onClick={onMenuClick}
        className="lg:hidden btn-ghost h-8 w-8 p-0 justify-center flex-shrink-0"
        aria-label="Open navigation"
      >
        <Menu size={16} />
      </button>

      {/* Page title / breadcrumb */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-xs text-tx-muted mb-0.5">
          <span>Costorah</span>
          {breadcrumb.slice(0, -1).map((seg, i) => (
            <span key={i} className="flex items-center gap-1.5">
              <span>/</span>
              <span className="capitalize">{seg}</span>
            </span>
          ))}
        </div>
        <h1 className="text-sm font-semibold text-tx-primary leading-tight">{pageLabel}</h1>
      </div>

      {/* Search / quick-jump trigger — full bar on md+, icon-only on mobile */}
      <button
        onClick={() => setCommandOpen(true)}
        className="hidden md:flex items-center gap-2 h-8 px-3 w-56 rounded-lg border border-border-subtle
                   bg-app-bg text-tx-muted text-xs hover:border-brand/40 hover:text-tx-secondary
                   transition-colors duration-fast"
      >
        <Search size={13} />
        <span className="flex-1 text-left">Search pages…</span>
        <kbd className="px-1.5 h-4.5 rounded border border-border-subtle text-[9px] leading-none flex items-center">
          ⌘K
        </kbd>
      </button>
      <button
        onClick={() => setCommandOpen(true)}
        className="md:hidden btn-ghost h-8 w-8 p-0 justify-center flex-shrink-0"
        aria-label="Search pages"
      >
        <Search size={16} />
      </button>

      {/* Controls */}
      <div className="flex items-center gap-1 sm:gap-2">
        {/* Date range picker */}
        <div className="relative" ref={dateRef}>
          <button
            onClick={() => { setDateOpen((o) => !o); setCurrencyOpen(false); }}
            aria-haspopup="listbox"
            aria-expanded={dateOpen}
            className={cn(
              "btn-outline h-8 text-xs px-2 sm:px-3",
              dateOpen && "border-brand text-tx-primary",
            )}
          >
            <Calendar size={13} />
            <span className="hidden sm:inline">{currentPreset?.label ?? datePreset}</span>
            <ChevronDown size={13} className={cn("hidden sm:block transition-transform", dateOpen && "rotate-180")} />
          </button>
          <Popover
            anchorRef={dateRef}
            open={dateOpen}
            onClose={() => setDateOpen(false)}
            align="end"
            className="w-44 glass-card rounded-xl shadow-elevated z-[1000] py-1.5 origin-top-right"
          >
            <div role="listbox">
              {DATE_PRESETS.map((p) => (
                <button
                  key={p.value}
                  role="option"
                  aria-selected={p.value === datePreset}
                  onClick={() => selectPreset(p)}
                  className={cn(
                    "w-full text-left px-3 py-2 text-xs transition-colors rounded-md mx-1 w-[calc(100%-8px)]",
                    p.value === datePreset
                      ? "text-brand bg-brand-subtle font-medium"
                      : "text-tx-secondary hover:text-tx-primary hover:bg-app-hover",
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </Popover>
        </div>

        {/* Currency selector */}
        <div className="relative" ref={currencyRef}>
          <button
            onClick={() => { setCurrencyOpen((o) => !o); setDateOpen(false); }}
            aria-haspopup="listbox"
            aria-expanded={currencyOpen}
            className={cn(
              "btn-outline h-8 text-xs px-2 sm:px-3",
              currencyOpen && "border-brand text-tx-primary",
            )}
          >
            <DollarSign size={13} />
            <span className="hidden sm:inline">{currency}</span>
            <ChevronDown size={13} className={cn("hidden sm:block transition-transform", currencyOpen && "rotate-180")} />
          </button>
          <Popover
            anchorRef={currencyRef}
            open={currencyOpen}
            onClose={() => setCurrencyOpen(false)}
            align="end"
            className="w-28 glass-card rounded-xl shadow-elevated z-[1000] py-1.5 origin-top-right"
          >
            <div role="listbox">
              {CURRENCIES.map((c) => (
                <button
                  key={c}
                  role="option"
                  aria-selected={c === currency}
                  onClick={() => { setCurrency(c); setCurrencyOpen(false); }}
                  className={cn(
                    "w-full text-left px-3 py-2 text-xs transition-colors rounded-md mx-1 w-[calc(100%-8px)]",
                    c === currency
                      ? "text-brand bg-brand-subtle font-medium"
                      : "text-tx-secondary hover:text-tx-primary hover:bg-app-hover",
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
          </Popover>
        </div>

        <div className="w-px h-5 bg-border-subtle" />

        {/* Theme switcher */}
        <ThemeSwitcher />

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => { setNotifOpen((o) => !o); setDateOpen(false); setCurrencyOpen(false); }}
            aria-haspopup="true"
            aria-expanded={notifOpen}
            aria-label="Notifications"
            className={cn("btn-ghost h-8 w-8 p-0 justify-center", notifOpen && "text-brand bg-app-hover")}
          >
            <Bell size={16} />
          </button>
          <Popover
            anchorRef={notifRef}
            open={notifOpen}
            onClose={() => setNotifOpen(false)}
            align="end"
            className="w-72 glass-card rounded-xl shadow-elevated z-[1000] origin-top-right overflow-hidden"
          >
            <div className="px-4 py-3 border-b border-border-subtle">
              <h3 className="text-sm font-semibold text-tx-primary">Notifications</h3>
            </div>
            <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
              <div className="w-10 h-10 rounded-xl bg-app-muted flex items-center justify-center mb-3">
                <BellOff size={18} className="text-tx-muted" />
              </div>
              <p className="text-sm font-medium text-tx-primary mb-1">You&apos;re all caught up</p>
              <p className="text-xs text-tx-muted leading-relaxed">No new notifications right now.</p>
            </div>
          </Popover>
        </div>
      </div>
    </header>
  );
}
