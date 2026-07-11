import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Archive,
  AlertTriangle,
  Bell,
  BellOff,
  Search,
  ChevronDown,
  Calendar,
  DollarSign,
  Info,
  Menu,
  OctagonAlert,
  Radio,
  X,
} from "lucide-react";
import { cn, getDaysAgo, getToday, subtractDays, toISODate } from "../utils";
import { useUIStore } from "../stores/ui";
import { useOrgStore } from "../stores/org";
import { routeLabel } from "../lib/navigation";
import { useAlerts, type AlertSeverity } from "../hooks/useAlerts";
import { useAlertActions } from "../hooks/useAlertsHistory";
import { useNotificationStore } from "../stores/notifications";
import ThemeSwitcher from "../components/ThemeSwitcher";
import ConnectionIndicator from "../components/ConnectionIndicator";
import Popover from "../components/Popover";
import type { Currency } from "../types/api";

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

const SEVERITY_ICON: Record<AlertSeverity, { icon: React.ElementType; className: string }> = {
  danger:  { icon: OctagonAlert,  className: "text-danger" },
  warning: { icon: AlertTriangle, className: "text-warning" },
  info:    { icon: Info,          className: "text-info" },
};

export default function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();
  const { currency, setCurrency, datePreset, setDateRange, setCommandOpen } = useUIStore();
  const { alerts, unreadCount } = useAlerts();
  const { markRead, markAllRead, dismiss, clearAll } = useNotificationStore();
  const { archive: archiveAlert } = useAlertActions();
  const [dateOpen, setDateOpen] = useState(false);
  const [currencyOpen, setCurrencyOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifSearch, setNotifSearch] = useState("");
  const [notifSeverity, setNotifSeverity] = useState<AlertSeverity | "all">("all");
  const dateRef = useRef<HTMLDivElement>(null);
  const currencyRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  const isPersonal = useOrgStore((s) => s.isPersonal);
  const pageLabel = routeLabel(location.pathname, isPersonal) ?? "Dashboard";
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

  const filteredAlerts = alerts.filter((a) => {
    if (notifSeverity !== "all" && a.severity !== notifSeverity) return false;
    if (!notifSearch.trim()) return true;
    const q = notifSearch.trim().toLowerCase();
    return a.title.toLowerCase().includes(q) || a.description.toLowerCase().includes(q);
  });

  /** Archive = dismiss locally, plus a REST dismiss for alerts the backend
   * actually persisted (those carrying a real `alertId`; see
   * DerivedAlert.alertId's doc comment) — client-derived budget/anomaly
   * alerts have no backend row, so archiving those is local-only. */
  function handleArchive(a: (typeof alerts)[number]) {
    dismiss(a.id);
    if (a.alertId) archiveAlert.mutate(a.alertId);
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
                    "w-[calc(100%-8px)] text-left px-3 py-2 text-xs transition-colors rounded-md mx-1",
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
                    "w-[calc(100%-8px)] text-left px-3 py-2 text-xs transition-colors rounded-md mx-1",
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

        {/* Real-time connection status */}
        <ConnectionIndicator />

        {/* Theme switcher */}
        <ThemeSwitcher />

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => { setNotifOpen((o) => !o); setDateOpen(false); setCurrencyOpen(false); }}
            aria-haspopup="true"
            aria-expanded={notifOpen}
            aria-label={unreadCount > 0 ? `Notifications — ${unreadCount} unread` : "Notifications"}
            className={cn("btn-ghost h-8 w-8 p-0 justify-center relative", notifOpen && "text-brand bg-app-hover")}
          >
            <Bell size={16} />
            {unreadCount > 0 && (
              <span
                aria-hidden="true"
                className="absolute -top-0.5 -right-0.5 min-w-[15px] h-[15px] px-0.5 rounded-full bg-danger
                           text-white text-[9px] font-bold flex items-center justify-center leading-none"
              >
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>
          <Popover
            anchorRef={notifRef}
            open={notifOpen}
            onClose={() => setNotifOpen(false)}
            align="end"
            className="w-72 glass-card rounded-xl shadow-elevated z-[1000] origin-top-right overflow-hidden"
          >
            <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-tx-primary">Alerts</h3>
              <div className="flex items-center gap-2.5">
                {unreadCount > 0 && (
                  <button
                    onClick={() => markAllRead(alerts.map((a) => a.id))}
                    className="text-[11px] font-medium text-brand hover:text-brand-light transition-colors duration-fast"
                  >
                    Mark all read
                  </button>
                )}
                {alerts.length > 0 && (
                  <button
                    onClick={() => clearAll(alerts.map((a) => a.id))}
                    className="text-[11px] font-medium text-tx-muted hover:text-tx-primary transition-colors duration-fast"
                  >
                    Clear all
                  </button>
                )}
              </div>
            </div>
            {alerts.length > 0 && (
              <div className="px-4 py-2 border-b border-border-subtle flex items-center gap-2">
                <div className="relative flex-1 min-w-0">
                  <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-tx-muted" />
                  <input
                    type="text"
                    value={notifSearch}
                    onChange={(e) => setNotifSearch(e.target.value)}
                    placeholder="Search alerts…"
                    aria-label="Search alerts"
                    className="w-full pl-6 pr-2 py-1 text-[11px] rounded-md bg-app-muted border border-border-subtle
                               text-tx-primary placeholder:text-tx-muted focus:outline-none focus:ring-1 focus:ring-brand"
                  />
                </div>
                <select
                  value={notifSeverity}
                  onChange={(e) => setNotifSeverity(e.target.value as AlertSeverity | "all")}
                  aria-label="Filter by severity"
                  className="text-[11px] rounded-md bg-app-muted border border-border-subtle text-tx-primary
                             px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-brand"
                >
                  <option value="all">All</option>
                  <option value="danger">Danger</option>
                  <option value="warning">Warning</option>
                  <option value="info">Info</option>
                </select>
              </div>
            )}
            {alerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
                <div className="w-10 h-10 rounded-xl bg-app-muted flex items-center justify-center mb-3">
                  <BellOff size={18} className="text-tx-muted" />
                </div>
                <p className="text-sm font-medium text-tx-primary mb-1">All clear</p>
                <p className="text-xs text-tx-muted leading-relaxed">
                  No budget, anomaly, or live alerts right now.
                </p>
              </div>
            ) : filteredAlerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
                <p className="text-xs text-tx-muted">No alerts match your search/filter.</p>
              </div>
            ) : (
              <ul className="max-h-80 overflow-y-auto py-1" aria-label="Alerts">
                {filteredAlerts.map((a) => {
                  const { icon: Icon, className } = SEVERITY_ICON[a.severity];
                  return (
                    <li key={a.id} className="group relative">
                      <button
                        onClick={() => markRead(a.id)}
                        className={cn(
                          "w-full flex items-start gap-2.5 px-4 py-2.5 text-left transition-colors duration-fast hover:bg-app-hover",
                          a.read && "opacity-55",
                        )}
                      >
                        {a.category === "live" ? (
                          <Radio size={14} className={cn("mt-0.5 flex-shrink-0", className)} />
                        ) : (
                          <Icon size={14} className={cn("mt-0.5 flex-shrink-0", className)} />
                        )}
                        <span className="min-w-0 flex-1 pr-9">
                          <span className="block text-xs font-medium text-tx-primary">{a.title}</span>
                          <span className="block text-[11px] text-tx-muted mt-0.5 leading-relaxed">{a.description}</span>
                        </span>
                        {!a.read && (
                          <span className="w-1.5 h-1.5 rounded-full bg-brand mt-1.5 flex-shrink-0" aria-label="Unread" />
                        )}
                      </button>
                      <div className="absolute right-2.5 top-2.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-fast">
                        <button
                          onClick={(e) => { e.stopPropagation(); handleArchive(a); }}
                          aria-label={`Archive: ${a.title}`}
                          title="Archive"
                          className="text-tx-muted hover:text-tx-primary p-0.5"
                        >
                          <Archive size={12} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); dismiss(a.id); }}
                          aria-label={`Dismiss: ${a.title}`}
                          title="Dismiss"
                          className="text-tx-muted hover:text-tx-primary p-0.5"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="px-4 py-2 border-t border-border-subtle">
              <p className="text-[10px] text-tx-muted">
                Budget and anomaly alerts are derived from spend data for the selected period;
                live alerts arrive over the real-time connection as they happen.
              </p>
            </div>
          </Popover>
        </div>
      </div>
    </header>
  );
}
