import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from "recharts";
import { motion, AnimatePresence } from "framer-motion";
import {
  DollarSign,
  Activity,
  Layers,
  Zap,
  Download,
  Radio,
  PlugZap,
  ShieldCheck,
  Sparkles,
  CheckCircle2,
  Circle,
  BarChart3,
  CalendarDays,
  CalendarClock,
  FolderKanban,
  Upload,
  RotateCw,
  AlertTriangle,
  Wallet,
  AlertOctagon,
  Bell,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Minus,
  Info,
  X,
  EyeOff,
  Rocket,
} from "lucide-react";
import ChartCard from "../components/ChartCard";
import LiveActivityFeed from "../components/LiveActivityFeed";
import CriticalAlertBanner from "../components/CriticalAlertBanner";
import ProviderLogo from "../components/ProviderLogo";
import { PROVIDER_COLORS, CONNECTABLE_PROVIDERS } from "../lib/providerCatalog";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import {
  useOverview,
  useTimeSeries,
  useProviders,
  useModels,
  useActivityFeed,
} from "../hooks/useDashboard";
import { useDashboardState, type DashboardSetupState } from "../hooks/useDashboardState";
import { useBudgetSummary } from "../hooks/useBudgets";
import { useOnboardingWidgetStore } from "../stores/onboardingWidget";
import { useLiveMetrics, useConnectionStatus } from "../realtime/hooks";
import {
  formatCost,
  formatDate,
  formatDateTime,
  formatTokens,
  formatNumber,
  modelDisplayName,
  providerDisplayName,
  cn,
} from "../utils";
import { useUIStore } from "../stores/ui";
import { useChartChrome } from "../lib/chartPalette";
import { toast } from "../stores/toast";
import type { Granularity, ActivityRunItem, ActivityFailureItem, OverviewKPIs } from "../types/api";
import type { BudgetSummaryResponse } from "../services/api";

// EP-22.3 — Intelligent Dashboard Empty States & Guided First Experience.
//
// Supersedes the EP-21.3 two-item version of this component (connect a
// provider / create a project) with the full 5-step checklist the product
// spec names. Reuses the exact same `useDashboardState()` signals the
// dashboard-state-machine hero below reads — one source of truth for
// "what has this organization actually done," computed from existing
// endpoints only (provider connections, projects, dashboard overview),
// never a second, parallel piece of progress state.
interface ChecklistItem {
  label: string;
  done: boolean;
  to: string;
  /** Shown under the label when the item can't be checked off — e.g.
   * "usage can never be imported for this provider," not just "not done
   * yet." EP-26.0.3.2. */
  note?: string | undefined;
  /** Overrides `to`'s destination and the "Go" button's label — used
   * alongside `note` so a permanently-blocked item (e.g. no historical
   * usage API) still offers a real next action instead of a dead end.
   * EP-26.0.3.3 — AI Playground now exists, so "generate usage yourself"
   * is a real, working link, not aspirational copy. */
  noteAction?: { to: string; label: string } | undefined;
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-app-bg p-3">
      <p className="text-[10px] text-tx-muted uppercase tracking-wide">{label}</p>
      <p className="mt-1 font-display text-lg font-semibold text-tx-primary tabular-nums">{value}</p>
    </div>
  );
}

// EP-25.4.4 Part 1/7 — replaces the permanent checklist with a genuine
// "you're done" state once setup is complete, instead of the checklist
// simply vanishing (EP-22.3's prior behavior). Every figure here is real
// data already fetched by the parent (`Overview()`) or by
// `useDashboardState()` — nothing is fabricated for this card.
function WorkspaceReadyCard({
  providersConnected,
  projects,
  models,
  todayCost,
  currency,
  lastSyncLabel,
}: {
  providersConnected: number;
  projects: number;
  models: number;
  todayCost: string;
  currency: string;
  lastSyncLabel: string | null;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-card-lg border border-border-subtle p-5 sm:p-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-success-dim flex items-center justify-center flex-shrink-0">
          <CheckCircle2 size={20} className="text-success" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-tx-primary">Workspace Ready</h3>
          <p className="text-xs text-tx-muted mt-0.5">
            Setup is complete — here&apos;s your workspace at a glance.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
        <StatTile label="Providers Connected" value={providersConnected} />
        <StatTile label="Projects" value={projects} />
        <StatTile label="Models" value={models} />
        <StatTile label="Today's Usage" value={formatCost(todayCost, currency, true)} />
      </div>
      <p className="text-[11px] text-tx-muted mb-4">Last sync: {lastSyncLabel ?? "never"}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/playground" className="btn-primary h-9 px-4 text-xs inline-flex items-center gap-1.5">
          <Rocket size={13} /> Open Playground
        </Link>
        <Link to="/analytics" className="btn-outline h-9 px-4 text-xs">
          Analytics
        </Link>
        <Link to="/connections" className="btn-outline h-9 px-4 text-xs">
          Connections
        </Link>
      </div>
    </motion.div>
  );
}

// EP-22.3 / EP-25.4.4 — the dashboard's Getting Started widget. Shows a
// checklist while setup is incomplete; once every step is done, replaces
// itself with `WorkspaceReadyCard` instead of quietly disappearing. Every
// signal is derived from `useDashboardState()` (provider connections,
// projects, dashboard overview — no duplicate progress state) plus the
// real, persisted `visitedAnalytics` flag from `useOnboardingWidgetStore`
// (EP-25.4.4 Part 2's "smart completion" for "View Analytics").
export function OnboardingWidget({
  kpi,
  lastSyncAt,
}: {
  kpi?: OverviewKPIs | undefined;
  lastSyncAt?: string | null;
}) {
  const progress = useDashboardState();
  const { currency } = useUIStore();
  const neverShow = useOnboardingWidgetStore((s) => s.neverShow);
  const dismissed = useOnboardingWidgetStore((s) => s.dismissed);
  const visitedAnalytics = useOnboardingWidgetStore((s) => s.visitedAnalytics);
  const dismiss = useOnboardingWidgetStore((s) => s.dismiss);
  const setNeverShow = useOnboardingWidgetStore((s) => s.setNeverShow);

  if (progress.isLoading || neverShow) return null;

  const {
    hasConnections,
    connectionsCount,
    hasValidatedConnection,
    hasProjects,
    projectsCount,
    hasUsage,
    hasUsageCapableConnection,
  } = progress;

  // EP-25.4.4 Part 1/2 — "setup complete" now also requires the user to
  // have actually opened Analytics at least once, not just that usage
  // exists — see useOnboardingWidgetStore's own header comment for why
  // this supersedes EP-22.3's original "no separate flag" decision.
  const allDone = hasConnections && hasValidatedConnection && hasProjects && hasUsage && visitedAnalytics;

  if (allDone) {
    return (
      <WorkspaceReadyCard
        providersConnected={connectionsCount}
        projects={projectsCount}
        models={kpi?.active_models ?? 0}
        todayCost={kpi?.today_cost ?? "0"}
        currency={currency}
        lastSyncLabel={lastSyncAt ? formatDateTime(lastSyncAt) : null}
      />
    );
  }

  if (dismissed) return null;

  // EP-26.0.3.2 — a validated connection whose provider has no bulk usage
  // API (Google/Azure/Grok/Ollama) can never make "Generate AI Usage"
  // complete on its own. Rather than leaving that item looking like an
  // indefinitely-stuck todo, disclose why once the connection is validated
  // but usage genuinely can't come from it.
  const usageWillNeverArrive = hasValidatedConnection && !hasUsageCapableConnection && !hasUsage;
  const usageNote = usageWillNeverArrive
    ? "Connected provider doesn't expose historical usage — this is expected, not an error."
    : undefined;
  // EP-26.0.3.3 — AI Playground (EP-25.4) is the real, working way to
  // generate tracked usage for a provider with no bulk usage-history API,
  // so a permanently-blocked "Generate AI Usage" item now points there
  // instead of leaving the user with a note and no action.
  const playgroundAction = usageWillNeverArrive
    ? { to: "/playground", label: "Playground" }
    : undefined;

  const items: ChecklistItem[] = [
    { label: "Connect Provider", done: hasConnections, to: "/connections" },
    { label: "Validate Provider", done: hasValidatedConnection, to: "/connections" },
    { label: "Create Project", done: hasProjects, to: "/projects" },
    {
      label: "Generate AI Usage",
      done: hasUsage,
      to: "/playground",
      note: usageNote,
      noteAction: playgroundAction,
    },
    // EP-25.4.4 Part 2 — "View Analytics" is now a real, independently
    // trackable action (has the user opened /analytics at least once),
    // not a mirror of "Generate AI Usage" — a user can complete this step
    // regardless of whether usage exists yet.
    { label: "View Analytics", done: visitedAnalytics, to: "/analytics" },
  ];
  const doneCount = items.filter((i) => i.done).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-card-lg border border-border-subtle p-5 sm:p-6"
    >
      <div className="flex items-center justify-between gap-4 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-tx-primary">Getting Started</h3>
          <p className="text-xs text-tx-muted mt-0.5">
            {doneCount} of {items.length} steps complete
          </p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="w-24 h-1.5 rounded-full bg-app-muted overflow-hidden" aria-hidden="true">
            <div
              className="h-full bg-brand rounded-full transition-all duration-500"
              style={{ width: `${(doneCount / items.length) * 100}%` }}
            />
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setNeverShow(true)}
              className="p-1 text-tx-muted hover:text-tx-primary"
              aria-label="Never show this again"
              title="Never show this again — reset from Settings > Preferences"
            >
              <EyeOff size={13} />
            </button>
            <button
              type="button"
              onClick={dismiss}
              className="p-1 text-tx-muted hover:text-tx-primary"
              aria-label="Dismiss"
              title="Dismiss for this session"
            >
              <X size={13} />
            </button>
          </div>
        </div>
      </div>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li
            key={item.label}
            className="flex items-center justify-between gap-3 rounded-lg px-2.5 py-2 -mx-2.5 hover:bg-app-hover/40 transition-colors duration-fast"
          >
            <div className="flex items-start gap-2.5 min-w-0">
              {item.done ? (
                <CheckCircle2 size={16} className="text-success flex-shrink-0 mt-0.5" />
              ) : (
                <Circle size={16} className="text-tx-muted flex-shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <span
                  className={cn(
                    "text-sm truncate block",
                    item.done ? "text-tx-muted line-through" : "text-tx-primary font-medium",
                  )}
                >
                  {item.label}
                </span>
                {!item.done && item.note && (
                  <span className="text-[11px] text-tx-muted leading-snug block mt-0.5">
                    {item.note}
                  </span>
                )}
              </div>
            </div>
            {!item.done && (!item.note || item.noteAction) && (
              <Link
                to={item.noteAction?.to ?? item.to}
                className="btn-outline h-7 px-3 text-[11px] flex-shrink-0 whitespace-nowrap"
              >
                {item.noteAction?.label ?? "Go"}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </motion.div>
  );
}

// EP-22.3 — Dashboard State Machine hero. Renders in place of "everything
// looks empty" for states 1-3; returns null once usage exists (state 4),
// letting the full KPI/chart dashboard below carry the page on its own.
export function DashboardStateHero({
  state,
  usageCapable = true,
}: {
  state: DashboardSetupState;
  /** False when every validated connection is for a provider with no bulk
   * usage-history API (Google/Azure/Grok/Ollama) — state 3's copy must not
   * imply usage is merely delayed when it can never arrive. EP-26.0.3.2. */
  usageCapable?: boolean;
}) {
  if (state === 4) return null;

  if (state === 1) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-card-lg border border-border-subtle p-6 sm:p-10 text-center"
      >
        <div className="w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center mx-auto mb-4">
          <PlugZap size={24} className="text-brand" />
        </div>
        <h2 className="font-display text-xl sm:text-2xl font-bold text-tx-primary mb-2">
          Welcome to Costorah
        </h2>
        <p className="text-sm text-tx-muted max-w-md mx-auto leading-relaxed mb-6">
          You&apos;re one step away from tracking AI costs. Connect your first provider to begin
          monitoring AI usage.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2.5">
          <Link to="/connections" className="btn-primary h-10 px-5 text-sm">
            Connect Provider
          </Link>
          <a
            href="https://costorah.com/features"
            target="_blank"
            rel="noreferrer"
            className="btn-outline h-10 px-5 text-sm"
          >
            Learn More
          </a>
        </div>
      </motion.div>
    );
  }

  if (state === 2) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-card-lg border border-border-subtle p-6 sm:p-10 text-center"
      >
        <div className="w-14 h-14 rounded-2xl bg-warning-dim flex items-center justify-center mx-auto mb-4">
          <ShieldCheck size={24} className="text-warning" />
        </div>
        <h2 className="font-display text-xl sm:text-2xl font-bold text-tx-primary mb-2">
          Provider connected
        </h2>
        <p className="text-sm text-tx-muted max-w-md mx-auto leading-relaxed mb-6">
          Validate your API credentials to begin collecting usage.
        </p>
        <Link to="/connections" className="btn-primary h-10 px-5 text-sm inline-flex">
          Validate Connection
        </Link>
      </motion.div>
    );
  }

  // state === 3
  //
  // EP-26.0.3.2 — a validated connection that lacks a bulk usage API
  // (Google/Azure/Grok/Ollama) will NEVER produce usage on its own — this
  // is the honest branch, distinct from the general "waiting for your
  // first request" copy below, which only applies to providers that
  // genuinely sync usage automatically once requests happen.
  if (!usageCapable) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-card-lg border border-border-subtle p-6 sm:p-10 text-center"
      >
        <div className="w-14 h-14 rounded-2xl bg-info-dim flex items-center justify-center mx-auto mb-4">
          <Info size={24} className="text-info" />
        </div>
        <h2 className="font-display text-xl sm:text-2xl font-bold text-tx-primary mb-2">
          Connected — historical usage unavailable
        </h2>
        <p className="text-sm text-tx-muted max-w-md mx-auto leading-relaxed mb-4">
          Your provider is connected, healthy, and its models have been discovered. This provider
          doesn&apos;t expose a bulk usage-history API, so Costorah has nothing to import from it
          automatically — that&apos;s expected, not an error, and won&apos;t change over time.
        </p>
        <ul className="text-sm text-tx-muted max-w-sm mx-auto text-left mb-6 flex flex-col gap-1.5">
          <li className="flex items-center gap-2">
            <CheckCircle2 size={14} className="text-success flex-shrink-0" /> Connected &amp; healthy
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle2 size={14} className="text-success flex-shrink-0" /> Models discovered
          </li>
          <li className="flex items-center gap-2">
            <Info size={14} className="text-info flex-shrink-0" /> Historical usage unavailable from this provider
          </li>
        </ul>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2.5">
          <Link to="/playground" className="btn-primary h-10 px-5 text-sm inline-flex">
            Generate usage with AI Playground
          </Link>
          <Link to="/connections" className="btn-outline h-10 px-5 text-sm inline-flex">
            View Providers
          </Link>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-card-lg border border-border-subtle p-6 sm:p-10 text-center"
    >
      <div className="w-14 h-14 rounded-2xl bg-success-dim flex items-center justify-center mx-auto mb-4">
        <Sparkles size={24} className="text-success" />
      </div>
      <h2 className="font-display text-xl sm:text-2xl font-bold text-tx-primary mb-2">
        Everything is ready.
      </h2>
      <p className="text-sm text-tx-muted max-w-md mx-auto leading-relaxed mb-4">
        Waiting for your applications to send AI requests. Costorah will automatically begin
        collecting:
      </p>
      <ul className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 text-xs text-tx-secondary mb-6 max-w-md mx-auto">
        {["Token usage", "Model usage", "Request count", "Spending", "Trends"].map((label) => (
          <li key={label} className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-brand" aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>
      <Link to="/connections" className="btn-primary h-10 px-5 text-sm inline-flex">
        View Providers
      </Link>
    </motion.div>
  );
}

// EP-22.3 — contextual replacements for ChartCard's generic "No data for
// this period" empty state, matched to the dashboard state machine so a
// brand-new org sees guidance instead of a dead end.
function SpendTrendEmpty({
  state,
  usageCapable = true,
}: {
  state: DashboardSetupState;
  usageCapable?: boolean;
}) {
  if (state === 1) {
    return (
      <div className="flex flex-col items-center text-center px-6">
        <div className="w-10 h-10 rounded-xl bg-brand-subtle flex items-center justify-center mb-3">
          <DollarSign size={18} className="text-brand" />
        </div>
        <p className="text-sm font-medium text-tx-primary mb-0.5">Start tracking AI spend.</p>
        <p className="text-xs text-tx-muted mb-4">Connect your first provider.</p>
        <Link to="/connections" className="btn-primary h-8 px-3.5 text-xs">
          Connect Provider
        </Link>
      </div>
    );
  }
  // EP-26.0.3.2 — consistent with DashboardStateHero's state-3 branch: a
  // usage-incapable provider will never populate this chart, so don't
  // imply it's merely a matter of time.
  if (state === 3 && !usageCapable) {
    return (
      <div className="flex flex-col items-center text-center px-6">
        <div className="w-10 h-10 rounded-xl bg-info-dim flex items-center justify-center mb-3">
          <Info size={18} className="text-info" />
        </div>
        <p className="text-sm font-medium text-tx-primary mb-0.5">Historical usage unavailable.</p>
        <p className="text-xs text-tx-muted max-w-xs leading-relaxed mb-4">
          Your connected provider doesn&apos;t expose a bulk usage-history API — this chart won&apos;t
          populate from it. This is expected, not an error.
        </p>
        <Link to="/playground" className="btn-outline h-8 px-3.5 text-xs">
          Generate usage with AI Playground
        </Link>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center text-center px-6">
      <div className="w-10 h-10 rounded-xl bg-app-muted flex items-center justify-center mb-3">
        <Radio size={18} className="text-tx-muted" />
      </div>
      <p className="text-sm font-medium text-tx-primary mb-0.5">Waiting for AI usage.</p>
      <p className="text-xs text-tx-muted max-w-xs leading-relaxed">
        Charts will automatically appear after your applications begin sending requests.
      </p>
    </div>
  );
}

function ProviderDistributionEmpty() {
  return (
    <div className="flex flex-col items-center text-center px-6">
      <div className="w-10 h-10 rounded-xl bg-brand-subtle flex items-center justify-center mb-3">
        <PlugZap size={18} className="text-brand" />
      </div>
      <p className="text-sm font-medium text-tx-primary mb-2">No providers connected.</p>
      <p className="text-[11px] text-tx-muted uppercase tracking-wide mb-1.5">Supported</p>
      <div className="flex flex-wrap items-center justify-center gap-1.5 mb-4 max-w-xs">
        {CONNECTABLE_PROVIDERS.map((p) => (
          <span
            key={p.value}
            className="text-[11px] px-2 py-0.5 rounded-full bg-app-muted text-tx-secondary"
          >
            {p.label}
          </span>
        ))}
      </div>
      <Link to="/connections" className="btn-primary h-8 px-3.5 text-xs">
        Add Provider
      </Link>
    </div>
  );
}

function TopModelsEmpty() {
  return (
    <div className="flex flex-col items-center text-center px-6">
      <div className="w-10 h-10 rounded-xl bg-app-muted flex items-center justify-center mb-3">
        <BarChart3 size={18} className="text-tx-muted" />
      </div>
      <p className="text-xs text-tx-muted leading-relaxed max-w-xs">
        Your highest-cost AI models will appear here automatically once requests are recorded.
      </p>
    </div>
  );
}

interface TooltipPayloadEntry {
  dataKey?: string | number;
  color?: string;
  name?: string | number;
  value?: string | number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string | number;
  currency: string;
}

function CustomTooltip({ active, payload, label, currency }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-card rounded-xl border-white/10 shadow-elevated p-3.5 min-w-[140px]">
      <p className="text-tx-muted text-[11px] uppercase tracking-wide mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color, boxShadow: `0 0 6px ${p.color}` }} />
          <span className="text-tx-secondary capitalize flex-1">{p.name}:</span>
          <span className="text-tx-primary font-semibold tabular-nums">
            {formatCost(p.value ?? 0, currency, true)}
          </span>
        </div>
      ))}
    </div>
  );
}

function GranularityTabs({
  value,
  onChange,
}: {
  value: Granularity;
  onChange: (v: Granularity) => void;
}) {
  const tabs: Granularity[] = ["daily", "weekly", "monthly"];
  return (
    <div className="flex items-center gap-1 bg-app-bg rounded-lg p-0.5">
      {tabs.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-150 capitalize
            ${value === t ? "bg-app-card text-tx-primary shadow-card" : "text-tx-muted hover:text-tx-secondary"}`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

// EP-24.1 — Recent Activity: latest imports, latest syncs, provider
// failures. Three compact columns reusing the app's existing list-row
// conventions (icon + text + timestamp) rather than a new list primitive.
function RunRow({ run }: { run: ActivityRunItem }) {
  const failed = run.status === "failed";
  return (
    <li className="flex items-center gap-2.5 py-2 border-b border-border-subtle last:border-0">
      <ProviderLogo providerId={run.provider} size="xs" bare />
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full flex-shrink-0",
          failed ? "bg-danger" : "bg-success",
        )}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-tx-primary truncate">
          {providerDisplayName(run.provider)}
        </p>
        <p className="text-[11px] text-tx-muted">
          {formatDateTime(run.startedAt)} · {run.eventsCollected} events
        </p>
      </div>
      {failed && <AlertTriangle size={13} className="text-danger flex-shrink-0" />}
    </li>
  );
}

function RecentActivitySection({
  imports,
  syncs,
  failures,
  loading,
}: {
  imports: ActivityRunItem[];
  syncs: ActivityRunItem[];
  failures: ActivityFailureItem[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="rounded-xl border border-border-subtle p-4 h-40 skeleton" />
        ))}
      </div>
    );
  }

  const nothing = imports.length === 0 && syncs.length === 0 && failures.length === 0;
  if (nothing) {
    return (
      <p className="text-xs text-tx-muted text-center py-6">
        No imports or syncs have run yet — background sync will populate this once connected
        providers start collecting usage.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="rounded-xl border border-border-subtle p-4">
        <div className="flex items-center gap-2 mb-2">
          <Upload size={14} className="text-brand" />
          <h4 className="text-xs font-semibold text-tx-primary">Latest Imports</h4>
        </div>
        {imports.length === 0 ? (
          <p className="text-[11px] text-tx-muted">No manual imports yet.</p>
        ) : (
          <ul>
            {imports.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-xl border border-border-subtle p-4">
        <div className="flex items-center gap-2 mb-2">
          <RotateCw size={14} className="text-brand" />
          <h4 className="text-xs font-semibold text-tx-primary">Latest Syncs</h4>
        </div>
        {syncs.length === 0 ? (
          <p className="text-[11px] text-tx-muted">No background syncs yet.</p>
        ) : (
          <ul>
            {syncs.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-xl border border-border-subtle p-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle size={14} className={failures.length > 0 ? "text-danger" : "text-tx-muted"} />
          <h4 className="text-xs font-semibold text-tx-primary">Provider Failures</h4>
        </div>
        {failures.length === 0 ? (
          <p className="text-[11px] text-tx-muted">No provider failures. All healthy.</p>
        ) : (
          <ul>
            {failures.map((f) => (
              <li
                key={f.connectionId}
                className="flex items-start gap-2.5 py-2 border-b border-border-subtle last:border-0"
              >
                <AlertTriangle size={13} className="text-danger flex-shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-tx-primary truncate">{f.displayName}</p>
                  <p className="text-[11px] text-tx-muted truncate">{f.lastError ?? "Unknown error"}</p>
                  {f.lastFailureAt && (
                    <p className="text-[10px] text-tx-muted mt-0.5">
                      {formatDateTime(f.lastFailureAt)} · {f.consecutiveFailureCount} consecutive
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ==========================================================================
 * EP-P2.1 — Overview page redesign (page-local composition components)
 *
 * The prior Overview was a flat vertical stack of sixteen equally-weighted
 * KPI cards (two identical 4-column grids) followed by linearly-stacked
 * charts — no visual hierarchy, no "north-star" metric, everything the same
 * size. These components introduce a modern enterprise composition:
 *   • a dominant SPEND hero (the number a FinOps user opens the page for)
 *   • a BUDGET-HEALTH guardrail beside it (spend + its limit, read together)
 *   • a compact SECONDARY-metric strip (usage/efficiency, lower emphasis)
 * All data is the exact same `useOverview()` / `useBudgetSummary()` output —
 * only the presentation and hierarchy change. No logic, queries, or
 * calculations are touched.
 * ========================================================================== */

/** Trend delta pill — up/down/flat, semantic-colored (with inverse support
 * for metrics where "down is good"). Same trend semantics MetricCard used. */
function Delta({ pct, inverse = false }: { pct: number | undefined; inverse?: boolean }) {
  if (pct === undefined) return null;
  const dir = pct > 0.1 ? "up" : pct < -0.1 ? "down" : "flat";
  const positive = inverse ? dir === "down" : dir === "up";
  const Icon = dir === "up" ? TrendingUpIcon : dir === "down" ? TrendingDownIcon : Minus;
  const cls =
    dir === "flat"
      ? "text-tx-muted bg-app-muted"
      : positive
        ? "text-success bg-success-dim"
        : "text-danger bg-danger-dim";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
        cls,
      )}
    >
      <Icon size={11} />
      {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

/** Wide, low sparkline for the spend hero (MetricCard's is not exported). */
function HeroSparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 168;
  const h = 52;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => [i * step, h - ((v - min) / range) * h] as const);
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible" aria-hidden="true">
      <defs>
        <linearGradient id="heroSpark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(var(--color-brand))" stopOpacity={0.3} />
          <stop offset="100%" stopColor="rgb(var(--color-brand))" stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#heroSpark)" />
      <path
        d={line}
        fill="none"
        stroke="rgb(var(--color-brand))"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function HeroSubStat({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-[11px] text-tx-muted">
        <Icon size={12} className="text-tx-muted" />
        {label}
      </p>
      <p className="mt-1 font-display text-lg font-semibold text-tx-primary tabular-nums">{value}</p>
    </div>
  );
}

/** The spend "north-star" — the single most-important number on the page,
 * given dominant size, its trend, a sparkline, and today/month context. */
function SpendSummaryPanel({
  kpi,
  currency,
  sparkline,
  loading,
}: {
  kpi: OverviewKPIs | undefined;
  currency: string;
  sparkline: number[];
  loading: boolean;
}) {
  return (
    <div className="glass-card metric-gradient-teal rounded-card-lg border border-brand/20 p-5 sm:p-6 relative overflow-hidden h-full flex flex-col">
      <div
        className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/50 to-transparent"
        aria-hidden="true"
      />
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-lg bg-brand-subtle text-brand flex-shrink-0">
              <DollarSign size={15} />
            </span>
            <span className="text-xs font-medium text-tx-muted">Total Spend</span>
            {!loading && <Delta pct={kpi?.cost_trend_pct ?? undefined} />}
          </div>
          {loading ? (
            <div className="mt-3 h-10 w-44 skeleton rounded" />
          ) : (
            <p className="mt-2.5 font-display text-[36px] leading-none font-bold text-tx-primary tabular-nums">
              {formatCost(kpi?.total_cost ?? "0", currency)}
            </p>
          )}
          <p className="mt-2 text-xs text-tx-muted">vs previous 30 days · {currency}</p>
        </div>
        <div className="hidden sm:block flex-shrink-0 self-center">
          {!loading && <HeroSparkline data={sparkline} />}
        </div>
      </div>
      <div className="mt-auto grid grid-cols-2 gap-4 border-t border-border-subtle pt-4">
        <HeroSubStat icon={CalendarClock} label="Today's Spend" value={formatCost(kpi?.today_cost ?? "0", currency)} />
        <HeroSubStat icon={CalendarDays} label="This Month" value={formatCost(kpi?.month_cost ?? "0", currency)} />
      </div>
    </div>
  );
}

/** Budget guardrail — pairs spend with its limit (utilization bar), the
 * forecast, and the two alert counts, so "am I on track?" is one glance. */
function BudgetHealthPanel({
  summary,
  currency,
  loading,
}: {
  summary: BudgetSummaryResponse | undefined;
  currency: string;
  loading: boolean;
}) {
  const budgeted = parseFloat(summary?.total_budgeted ?? "0");
  const spent = parseFloat(summary?.total_spent ?? "0");
  const pct = budgeted > 0 ? Math.min(100, Math.max(0, (spent / budgeted) * 100)) : 0;
  const critical = summary?.critical_alert_count ?? 0;
  const active = summary?.active_alert_count ?? 0;
  const barColor = pct >= 90 ? "bg-danger" : pct >= 75 ? "bg-warning" : "bg-brand";

  return (
    <div className="glass-card rounded-card-lg border border-border-subtle p-5 sm:p-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary-subtle text-primary-light flex-shrink-0">
            <Wallet size={15} />
          </span>
          <span className="text-xs font-medium text-tx-muted">Budget Health</span>
        </div>
        <Link to="/budgets" className="text-[11px] font-medium text-brand hover:text-brand-light">
          Manage
        </Link>
      </div>

      {loading ? (
        <div className="mt-4 h-9 w-32 skeleton rounded" />
      ) : budgeted > 0 ? (
        <>
          <p className="mt-3 font-display text-[26px] leading-none font-bold text-tx-primary tabular-nums">
            {formatCost(summary?.total_remaining ?? "0", currency)}
          </p>
          <p className="mt-1.5 text-xs text-tx-muted">
            remaining of {formatCost(summary?.total_budgeted ?? "0", currency)} budgeted
          </p>
          <div className="mt-3.5 h-2 rounded-full bg-app-muted overflow-hidden">
            <div className={cn("h-full rounded-full transition-all duration-slow", barColor)} style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-1.5 text-[11px] text-tx-muted tabular-nums">{pct.toFixed(0)}% of budget used</p>
        </>
      ) : (
        <div className="mt-3">
          <p className="text-sm font-medium text-tx-primary">No budgets set</p>
          <p className="mt-1 text-xs text-tx-muted leading-relaxed">
            Track spend against a limit and get alerted before you exceed it.
          </p>
          <Link to="/budgets" className="btn-outline h-8 px-3 text-xs mt-3 w-fit">
            Create budget
          </Link>
        </div>
      )}

      <div className="mt-auto grid grid-cols-2 gap-2.5 pt-4">
        <div className="rounded-xl border border-border-subtle bg-app-bg p-3">
          <div className="flex items-center gap-1.5 text-[11px] text-tx-muted">
            <Bell size={12} /> Active Alerts
          </div>
          <p className="mt-1 font-display text-lg font-semibold text-tx-primary tabular-nums">{active}</p>
        </div>
        <div className={cn("rounded-xl border p-3", critical > 0 ? "border-danger/30 bg-danger-dim" : "border-border-subtle bg-app-bg")}>
          <div className="flex items-center gap-1.5 text-[11px] text-tx-muted">
            <AlertOctagon size={12} className={critical > 0 ? "text-danger" : undefined} /> Critical Alerts
          </div>
          <p className={cn("mt-1 font-display text-lg font-semibold tabular-nums", critical > 0 ? "text-danger" : "text-tx-primary")}>
            {critical}
          </p>
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between rounded-xl border border-border-subtle bg-app-bg p-3">
        <div className="flex items-center gap-1.5 text-[11px] text-tx-muted">
          <TrendingUpIcon size={12} /> Projected EOM Spend
        </div>
        <p className="font-display text-sm font-semibold text-tx-primary tabular-nums">
          {formatCost(summary?.projected_eom_spend ?? "0", currency)}
        </p>
      </div>
    </div>
  );
}

/** Compact secondary metric — lower visual weight than the hero, for the
 * usage/efficiency numbers that support (not headline) the spend story. */
function SecondaryStat({
  icon: Icon,
  label,
  value,
  hint,
  trendPct,
  loading,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  hint?: string;
  trendPct?: number | undefined;
  loading?: boolean;
}) {
  return (
    <div className="glass-card rounded-card border border-border-subtle p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-tx-muted min-w-0">
          <Icon size={13} className="text-tx-muted flex-shrink-0" />
          <span className="truncate">{label}</span>
        </span>
        {!loading && trendPct !== undefined && <Delta pct={trendPct} />}
      </div>
      {loading ? (
        <div className="mt-2.5 h-6 w-20 skeleton rounded" />
      ) : (
        <p className="mt-2 font-display text-xl font-bold text-tx-primary tabular-nums leading-none">{value}</p>
      )}
      {hint && <p className="mt-1.5 text-[11px] text-tx-muted truncate">{hint}</p>}
    </div>
  );
}

/** Task-oriented quick actions — surfaces the FinOps workflows a user reaches
 * for from the Overview (test provider, set a budget, explore, prototype),
 * improving discoverability without duplicating the sidebar's full nav. */
function QuickActionsRow() {
  const actions = [
    { to: "/playground", icon: Rocket, label: "Playground" },
    { to: "/connections", icon: PlugZap, label: "Connections" },
    { to: "/budgets", icon: Wallet, label: "Budgets" },
    { to: "/analytics", icon: BarChart3, label: "Analytics" },
  ] as const;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {actions.map((a) => (
        <Link key={a.to} to={a.to} className="btn-outline h-9 px-3.5 text-sm">
          <a.icon size={14} /> {a.label}
        </Link>
      ))}
    </div>
  );
}

/** Lightweight group label — adds section grouping/hierarchy between the
 * hero band, the analytics charts, and the operational feeds. */
function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-widest text-tx-muted pt-1">{children}</h2>
  );
}

export default function Overview() {
  const { currency } = useUIStore();
  const chrome = useChartChrome();
  const tooltipStyle = {
    backgroundColor: chrome.tooltipBg,
    border: `1px solid ${chrome.tooltipBorder}`,
    borderRadius: 12,
    color: chrome.text,
    fontSize: 12,
    boxShadow: "0 12px 32px rgb(var(--shadow-rgb) / var(--shadow-a-5))",
    backdropFilter: "blur(12px)",
  };
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [hoveredProvider, setHoveredProvider] = useState<string | null>(null);
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);
  const liveMetrics = useLiveMetrics();
  const connection = useConnectionStatus();
  const dashboardState = useDashboardState();

  // EP-24.4.1: for a brand-new organization (dashboard state 1-3 — no
  // provider connected, or connected-but-unvalidated, or validated-but-
  // no-usage-yet), DashboardStateHero replaces this whole section with its
  // own guidance, so these four breakdown queries would just fetch empty
  // data nothing renders. Gating them on `state === 4` means a new
  // account's first dashboard load fires 4 fewer network requests. The KPI
  // cards below (via `overview`) and the budget summary always render, so
  // those two stay unconditional.
  const hasRealUsage = !dashboardState.isLoading && dashboardState.state === 4;

  const overview = useOverview();
  const timeSeries = useTimeSeries({}, { enabled: hasRealUsage });
  const providers = useProviders({}, { enabled: hasRealUsage });
  const models = useModels({}, { enabled: hasRealUsage });
  const activityFeed = useActivityFeed(8, { enabled: hasRealUsage });
  const budgetSummary = useBudgetSummary();

  const kpi = overview.data;
  const tsData = timeSeries.data?.data ?? [];
  const providerList = providers.data?.providers ?? [];
  const modelList = models.data?.models ?? [];

  // EP-25.4.4 — "Last Sync" for the Workspace Ready card: the most recent
  // real import/sync run timestamp, derived from the same activity feed
  // the "Sync Activity" section below already renders — no second query.
  const lastSyncAt = [...(activityFeed.data?.imports ?? []), ...(activityFeed.data?.syncs ?? [])]
    .map((r) => r.startedAt)
    .sort()
    .at(-1);

  // Sparklines derived from ts data (last 7 pts)
  const recent7 = tsData.slice(-7).map((d) => parseFloat(d.total_cost));

  const chartData = tsData.map((d) => ({
    date: formatDate(d.date),
    total: parseFloat(d.total_cost),
    ...Object.fromEntries(
      Object.entries(d.provider_breakdown).map(([k, v]) => [k, parseFloat(v)]),
    ),
  }));

  const pieData = providerList.map((p) => ({
    name: p.provider,
    value: parseFloat(p.total_cost),
  }));

  const tokenChartData = tsData.slice(-14).map((d) => ({
    date: formatDate(d.date),
    tokens: d.total_tokens,
  }));

  const topModels = [...modelList]
    .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost))
    .slice(0, 8)
    .map((m) => ({
      name: modelDisplayName(m.model_id).slice(0, 14),
      cost: parseFloat(m.total_cost),
    }));

  const hasData = providerList.length > 0 || tsData.length > 0;

  function exportReport() {
    if (!hasData) {
      toast.warning("Nothing to export", "There is no spend data for the selected period.");
      return;
    }
    const lines: string[] = [];
    lines.push("COSTORAH Spend Report");
    lines.push(`Currency,${currency}`);
    if (kpi) {
      lines.push("");
      lines.push("Summary");
      lines.push("Metric,Value");
      lines.push(`Total Spend,${kpi.total_cost}`);
      lines.push(`Today's Spend,${kpi.today_cost}`);
      lines.push(`This Month,${kpi.month_cost}`);
      lines.push(`Total Requests,${kpi.total_requests}`);
      lines.push(`Input Tokens,${kpi.total_input_tokens}`);
      lines.push(`Output Tokens,${kpi.total_output_tokens}`);
      lines.push(`Avg Cost / Request,${kpi.avg_cost_per_request}`);
      lines.push(`Active Providers,${kpi.active_providers}`);
      lines.push(`Active Models,${kpi.active_models}`);
      lines.push(`Projects,${kpi.active_projects}`);
    }
    lines.push("");
    lines.push("Spend by Provider");
    lines.push("Provider,Total Cost,Requests,Cost Share %");
    for (const p of providerList) {
      lines.push(`${providerDisplayName(p.provider)},${p.total_cost},${p.request_count},${p.cost_share_pct}`);
    }
    lines.push("");
    lines.push("Daily Spend");
    lines.push("Date,Total Cost,Total Tokens,Requests");
    for (const d of tsData) {
      lines.push(`${d.date},${d.total_cost},${d.total_tokens},${d.total_requests}`);
    }

    const csv = lines.join("\n");
    const a = document.createElement("a");
    a.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    a.download = `costorah-report-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    toast.success("Report ready", "Spend report exported to CSV.");
  }

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 sm:gap-6">
      <PageHeader
        title="Overview"
        description="Real-time AI spend across every provider and project."
        actions={
          <button
            onClick={exportReport}
            disabled={overview.isLoading}
            className="btn-outline h-9 text-sm px-3.5"
          >
            <Download size={14} /> Export report
          </button>
        }
      />

      <CriticalAlertBanner />

      <OnboardingWidget kpi={kpi} lastSyncAt={lastSyncAt ?? null} />

      {!dashboardState.isLoading && (
        <DashboardStateHero
          state={dashboardState.state}
          usageCapable={dashboardState.hasUsageCapableConnection}
        />
      )}

      {/* Live-update strip — appears once a usage.created event has landed
          since the socket connected; the KPI numbers below refresh via the
          normal query-invalidation path (see realtime/queryBridge.ts), this
          is just the "yes, something just happened" acknowledgment. */}
      <AnimatePresence>
        {connection.status === "connected" && liveMetrics.requestCount > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="flex items-center gap-2 text-xs text-tx-muted overflow-hidden"
          >
            <Radio size={12} className="text-brand flex-shrink-0" />
            <span>
              <span className="font-semibold text-tx-primary tabular-nums">
                +{formatNumber(liveMetrics.requestCount)}
              </span>{" "}
              request{liveMetrics.requestCount === 1 ? "" : "s"} ·{" "}
              <span className="font-semibold text-tx-primary tabular-nums">
                +{formatCost(liveMetrics.costDelta, currency, true)}
              </span>{" "}
              live since you opened this page
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── Quick actions — task-oriented shortcuts (EP-P2.1) ─────────── */}
      <QuickActionsRow />

      {/* ─── HERO BAND — the spend north-star paired with its budget
              guardrail. Replaces the previous flat 8-card grid: the number a
              FinOps user opens the page for now dominates, read side-by-side
              with how much of its budget is left. (EP-P2.1) ──────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5">
        <div className="lg:col-span-2">
          <SpendSummaryPanel
            kpi={kpi}
            currency={currency}
            sparkline={recent7}
            loading={overview.isLoading}
          />
        </div>
        <BudgetHealthPanel
          summary={budgetSummary.data}
          currency={currency}
          loading={budgetSummary.isLoading}
        />
      </div>

      {/* ─── Secondary metrics — usage & efficiency, lower visual weight than
              the hero (EP-P2.1). Every KPI the old grid showed is preserved,
              just re-ranked by importance. ─────────────────────────────── */}
      <div>
        <GroupLabel>Usage &amp; efficiency</GroupLabel>
        <div className="mt-2.5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <SecondaryStat
            icon={Layers}
            label="Total Tokens"
            value={formatTokens((kpi?.total_input_tokens ?? 0) + (kpi?.total_output_tokens ?? 0))}
            hint={`${formatTokens(kpi?.total_input_tokens ?? 0)} in · ${formatTokens(kpi?.total_output_tokens ?? 0)} out`}
            trendPct={kpi?.token_trend_pct ?? undefined}
            loading={overview.isLoading}
          />
          <SecondaryStat
            icon={Activity}
            label="Total Requests"
            value={formatNumber(kpi?.total_requests ?? 0)}
            hint="API calls processed"
            trendPct={kpi?.request_trend_pct ?? undefined}
            loading={overview.isLoading}
          />
          <SecondaryStat
            icon={PlugZap}
            label="Active Providers"
            value={formatNumber(kpi?.active_providers ?? 0)}
            hint={`${kpi?.active_models ?? 0} models in use`}
            loading={overview.isLoading}
          />
          <SecondaryStat
            icon={FolderKanban}
            label="Projects"
            value={formatNumber(kpi?.active_projects ?? 0)}
            hint="with recorded spend"
            loading={overview.isLoading}
          />
          <SecondaryStat
            icon={Zap}
            label="Avg Cost / Request"
            value={formatCost(kpi?.avg_cost_per_request ?? "0", currency)}
            hint="across all providers"
            loading={overview.isLoading}
          />
        </div>
      </div>

      {/* ─── Spend analytics group label (the charts that follow) ────────── */}
      <GroupLabel>Spend analytics</GroupLabel>

      {/* Cost Trend Chart */}
      <ChartCard
        title="Spend Trend"
        subtitle="Total AI spending over time with provider breakdown"
        loading={timeSeries.isLoading}
        error={timeSeries.error ? "Failed to load" : null}
        empty={chartData.length === 0}
        emptyContent={
          chartData.length === 0 ? (
            <SpendTrendEmpty
              state={dashboardState.state}
              usageCapable={dashboardState.hasUsageCapableConnection}
            />
          ) : undefined
        }
        actions={
          <GranularityTabs
            value={granularity}
            onChange={(g) => {
              setGranularity(g);
              useUIStore.getState().setGranularity(g);
            }}
          />
        }
        minHeight={300}
      >
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={chrome.brand} stopOpacity={0.3} />
                <stop offset="95%" stopColor={chrome.brand} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatCost(v, currency, true)}
              width={56}
            />
            <Tooltip content={<CustomTooltip currency={currency} />} cursor={{ stroke: chrome.brand, strokeWidth: 1, strokeDasharray: "3 3" }} />
            <Area
              type="monotone"
              dataKey="total"
              name="Total"
              stroke={chrome.brand}
              strokeWidth={2.5}
              fill="url(#totalGrad)"
              dot={false}
              activeDot={{ r: 5, fill: chrome.brand, stroke: chrome.bg, strokeWidth: 2 }}
              animationDuration={1000}
              animationEasing="ease-out"
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Provider + Model charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <ChartCard
          title="Provider Distribution"
          subtitle="Cost share by provider"
          loading={providers.isLoading}
          empty={pieData.length === 0}
          emptyContent={
            pieData.length === 0 && !dashboardState.hasConnections ? (
              <ProviderDistributionEmpty />
            ) : undefined
          }
          minHeight={260}
          bodyClassName="flex flex-col sm:flex-row items-center gap-2"
        >
          <div className="w-full sm:w-3/5">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={95}
                paddingAngle={3}
                dataKey="value"
                animationDuration={900}
                animationEasing="ease-out"
              >
                {pieData.map((entry) => {
                  const dimmed = hoveredProvider !== null && hoveredProvider !== entry.name;
                  return (
                    <Cell
                      key={entry.name}
                      fill={PROVIDER_COLORS[entry.name] ?? chrome.primary}
                      stroke="transparent"
                      opacity={dimmed ? 0.3 : 1}
                      style={{ transition: "opacity 150ms ease-out" }}
                      onMouseEnter={() => setHoveredProvider(entry.name)}
                      onMouseLeave={() => setHoveredProvider(null)}
                    />
                  );
                })}
              </Pie>
              <Tooltip
                formatter={(v: number) => formatCost(v, currency, true)}
                contentStyle={tooltipStyle}
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
              />
            </PieChart>
          </ResponsiveContainer>
          </div>

          {/* Interactive legend — hover highlights the matching slice */}
          <div className="flex sm:flex-col flex-wrap gap-2 sm:gap-1.5 sm:w-2/5 px-2">
            {pieData.map((entry) => {
              const total = pieData.reduce((s, p) => s + p.value, 0);
              const pct = total > 0 ? (entry.value / total) * 100 : 0;
              const dimmed = hoveredProvider !== null && hoveredProvider !== entry.name;
              return (
                <button
                  key={entry.name}
                  onMouseEnter={() => setHoveredProvider(entry.name)}
                  onMouseLeave={() => setHoveredProvider(null)}
                  className={cn(
                    "flex items-center gap-2 text-left px-2 py-1.5 rounded-lg transition-all duration-fast",
                    dimmed ? "opacity-40" : "opacity-100 bg-app-hover/60",
                  )}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: PROVIDER_COLORS[entry.name] ?? chrome.primary }}
                  />
                  <span className="text-xs text-tx-secondary flex-1 truncate">
                    {providerDisplayName(entry.name)}
                  </span>
                  <span className="text-xs font-semibold text-tx-primary tabular-nums">
                    {pct.toFixed(0)}%
                  </span>
                </button>
              );
            })}
          </div>
        </ChartCard>

        <ChartCard
          title="Top Models by Spend"
          subtitle="Highest cost AI models"
          loading={models.isLoading}
          empty={topModels.length === 0}
          emptyContent={topModels.length === 0 ? <TopModelsEmpty /> : undefined}
          minHeight={260}
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={topModels}
              layout="vertical"
              margin={{ top: 0, right: 16, bottom: 0, left: 4 }}
              onMouseLeave={() => setHoveredBar(null)}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: chrome.axis, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => formatCost(v, currency, true)}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: chrome.axis, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={90}
              />
              <Tooltip
                formatter={(v: number) => formatCost(v, currency, true)}
                contentStyle={tooltipStyle}
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
                cursor={{ fill: "rgb(var(--color-brand) / 0.06)" }}
              />
              <Bar
                dataKey="cost"
                name="Cost"
                radius={[0, 4, 4, 0]}
                animationDuration={800}
                animationEasing="ease-out"
                onMouseEnter={(_, index) => setHoveredBar(index)}
              >
                {topModels.map((entry, i) => (
                  <Cell
                    key={entry.name}
                    fill={hoveredBar === null || hoveredBar === i ? "rgb(var(--color-brand))" : "rgb(var(--color-brand) / 0.35)"}
                    style={{ transition: "fill 150ms ease-out" }}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Token Throughput */}
      <ChartCard
        title="Token Throughput"
        subtitle="Daily token volume across all providers"
        loading={timeSeries.isLoading}
        empty={tokenChartData.length === 0}
        minHeight={220}
      >
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={tokenChartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: chrome.axis, fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatTokens(v)}
              width={48}
            />
            <Tooltip
              formatter={(v: number) => formatTokens(v)}
              contentStyle={tooltipStyle}
              itemStyle={{ color: chrome.text }}
              labelStyle={{ color: chrome.text }}
              cursor={{ fill: "rgb(var(--color-brand) / 0.06)" }}
            />
            <Bar dataKey="tokens" name="Tokens" fill={chrome.brand} radius={[4, 4, 0, 0]} animationDuration={800} animationEasing="ease-out" />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Per-provider quick stats — only meaningful once usage exists; in
          states 1-3 the DashboardStateHero above already carries the
          page's guidance, so an empty stats grid would just be visual
          noise (EP-22.3: "only render charts when meaningful data
          exists"). */}
      {dashboardState.state === 4 && (
        <Section title="Provider Snapshot" description={`${formatNumber(kpi?.total_requests ?? 0)} total requests in the current period`}>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
            {providers.isLoading
              ? Array.from({ length: 6 }, (_, i) => (
                  <div key={i} className="rounded-xl border border-border-subtle p-3 h-[72px] skeleton" />
                ))
              : providerList.map((p) => (
                  <motion.div
                    key={p.provider}
                    whileHover={{ y: -2 }}
                    className="rounded-xl border border-border-subtle bg-app-bg p-3 transition-shadow duration-base hover:shadow-card"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <ProviderLogo providerId={p.provider} size="xs" bare />
                      <span className="truncate text-xs font-medium text-tx-secondary">
                        {providerDisplayName(p.provider)}
                      </span>
                    </div>
                    <p className="mt-2 font-display text-base font-semibold text-tx-primary tabular-nums">
                      {formatNumber(p.request_count, true)}
                    </p>
                    <p className="text-[10px] text-tx-muted">{p.cost_share_pct}% of spend</p>
                  </motion.div>
                ))}
          </div>
        </Section>
      )}

      {/* Recent Activity — EP-24.1: latest imports, syncs, and provider
          failures, backed by GET /v1/dashboard/activity (EP-08/EP-23.3/
          EP-23.4's UsageCollectionRun + EP-22's ProviderConnection failure
          fields). Distinct from the live WebSocket feed below — this
          section is about *background collection health*, not individual
          usage events. */}
      {dashboardState.state === 4 && (
        <Section title="Sync Activity" description="Latest imports, syncs, and provider failures">
          <RecentActivitySection
            imports={activityFeed.data?.imports ?? []}
            syncs={activityFeed.data?.syncs ?? []}
            failures={activityFeed.data?.failures ?? []}
            loading={activityFeed.isLoading}
          />
        </Section>
      )}

      {/* Live activity — live over WebSocket, falls back to polling */}
      {dashboardState.state === 4 && <LiveActivityFeed limit={10} />}
    </div>
  );
}
