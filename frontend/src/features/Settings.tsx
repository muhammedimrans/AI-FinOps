import { useState } from "react";
import { motion } from "framer-motion";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Settings as SettingsIcon,
  Globe,
  Bell,
  Palette,
  RefreshCw,
  Save,
  CheckCircle,
} from "lucide-react";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";
import type { Currency } from "../types/api";

const apiSchema = z.object({
  apiBaseUrl: z.string().url("Must be a valid URL"),
  timeout: z.number().min(1000).max(30000),
});

type ApiForm = z.infer<typeof apiSchema>;

const SECTIONS = [
  { id: "api",           label: "API",           icon: Globe },
  { id: "display",       label: "Display",       icon: Palette },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "data",          label: "Data",          icon: RefreshCw },
];

function SectionCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card border border-border-subtle p-6"
    >
      <h3 className="text-sm font-semibold text-tx-primary flex items-center gap-2 mb-5">
        <Icon size={14} className="text-tx-muted" />
        {title}
      </h3>
      <div className="space-y-5">{children}</div>
    </motion.div>
  );
}

function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-tx-primary font-medium">{label}</p>
        {description && <p className="text-xs text-tx-muted mt-0.5">{description}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={cn(
        "relative w-10 h-5.5 rounded-full transition-colors duration-200",
        value ? "bg-brand" : "bg-app-muted",
      )}
      aria-checked={value}
      role="switch"
    >
      <span
        className={cn(
          "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200",
          value ? "translate-x-5" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

export default function Settings() {
  const { theme, toggleTheme, currency, setCurrency } = useUIStore();
  const [active, setActive] = useState("api");
  const [saved, setSaved] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(300);
  const [notifs, setNotifs] = useState({ budget: true, anomaly: true, weekly: false, marketing: false });

  const { register, handleSubmit, setError, formState: { errors } } = useForm<ApiForm>({
    defaultValues: {
      apiBaseUrl: (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000",
      timeout: 10000,
    },
  });

  function onSave(data: ApiForm) {
    const result = apiSchema.safeParse(data);
    if (!result.success) {
      for (const issue of result.error.issues) {
        const field = issue.path[0];
        if (field === "apiBaseUrl" || field === "timeout") {
          setError(field, { message: issue.message });
        }
      }
      return;
    }
    console.info("Settings saved", result.data);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  return (
    <div className="p-4 sm:p-6 max-w-3xl">
      {/* Page header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-xl bg-brand-subtle flex items-center justify-center flex-shrink-0">
          <SettingsIcon size={18} className="text-brand" />
        </div>
        <div>
          <h2 className="text-h2 text-tx-primary">Settings</h2>
          <p className="text-xs text-tx-muted mt-0.5">Configure your AI FinOps workspace</p>
        </div>
      </div>

      {/* Section tabs */}
      <div className="flex flex-wrap gap-1 mb-6 bg-app-card rounded-lg p-1 w-fit border border-border-subtle">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setActive(s.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-md text-xs font-medium transition-all",
              active === s.id
                ? "bg-brand text-app-bg shadow-glow-brand"
                : "text-tx-secondary hover:text-tx-primary hover:bg-app-hover",
            )}
          >
            <s.icon size={12} />
            {s.label}
          </button>
        ))}
      </div>

      <div className="space-y-5">
        {active === "api" && (
          <form onSubmit={(e) => { void handleSubmit(onSave)(e); }}>
            <SectionCard title="API Configuration" icon={Globe}>
              <div>
                <label className="text-xs text-tx-muted block mb-1.5">Backend URL</label>
                <input
                  {...register("apiBaseUrl")}
                  className={cn(
                    "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary",
                    "placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors",
                    errors.apiBaseUrl ? "border-danger" : "border-border",
                  )}
                  placeholder="http://localhost:8000"
                />
                {errors.apiBaseUrl && (
                  <p className="text-danger text-xs mt-1">{errors.apiBaseUrl.message}</p>
                )}
              </div>
              <div>
                <label className="text-xs text-tx-muted block mb-1.5">Request Timeout (ms)</label>
                <input
                  type="number"
                  {...register("timeout", { valueAsNumber: true })}
                  className={cn(
                    "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary",
                    "focus:outline-none focus:border-brand transition-colors",
                    errors.timeout ? "border-danger" : "border-border",
                  )}
                />
                {errors.timeout && (
                  <p className="text-danger text-xs mt-1">{errors.timeout.message}</p>
                )}
              </div>
              <button
                type="submit"
                className={cn("btn-primary w-fit", saved && "bg-success hover:bg-success")}
              >
                {saved ? <CheckCircle size={14} /> : <Save size={14} />}
                {saved ? "Saved!" : "Save API Settings"}
              </button>
            </SectionCard>
          </form>
        )}

        {active === "display" && (
          <SectionCard title="Display Preferences" icon={Palette}>
            <SettingRow label="Theme" description="Dark or light interface">
              <div className="flex gap-1 bg-app-bg rounded-lg p-0.5 border border-border-subtle">
                {["dark", "light"].map((t) => (
                  <button
                    key={t}
                    onClick={() => { if (theme !== t) toggleTheme(); }}
                    className={cn(
                      "px-3 py-1 rounded-md text-xs font-medium transition-all capitalize",
                      theme === t ? "bg-brand text-app-bg" : "text-tx-muted hover:text-tx-secondary",
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </SettingRow>
            <SettingRow label="Currency" description="Default currency for cost display">
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value as Currency)}
                className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
              >
                {["USD", "EUR", "GBP"].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </SettingRow>
            <SettingRow label="Compact numbers" description="Show M/B/K abbreviations">
              <Toggle value={true} onChange={() => {}} />
            </SettingRow>
          </SectionCard>
        )}

        {active === "notifications" && (
          <SectionCard title="Notification Preferences" icon={Bell}>
            {[
              { key: "budget" as const,    label: "Budget alerts",    desc: "Alert when projects exceed 80% budget" },
              { key: "anomaly" as const,   label: "Anomaly detection",desc: "Notify on unusual cost spikes" },
              { key: "weekly" as const,    label: "Weekly digest",    desc: "Weekly cost summary email" },
              { key: "marketing" as const, label: "Product updates",  desc: "New features and announcements" },
            ].map((n) => (
              <SettingRow key={n.key} label={n.label} description={n.desc}>
                <Toggle
                  value={notifs[n.key]}
                  onChange={(v) => setNotifs((prev) => ({ ...prev, [n.key]: v }))}
                />
              </SettingRow>
            ))}
          </SectionCard>
        )}

        {active === "data" && (
          <SectionCard title="Data Settings" icon={RefreshCw}>
            <SettingRow label="Auto-refresh interval" description="How often to refresh dashboard data">
              <select
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(Number(e.target.value))}
                className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
              >
                <option value={60}>1 minute</option>
                <option value={300}>5 minutes</option>
                <option value={900}>15 minutes</option>
                <option value={1800}>30 minutes</option>
                <option value={0}>Manual only</option>
              </select>
            </SettingRow>
            <SettingRow label="Cache duration" description="Keep fetched data for">
              <select className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand">
                <option>5 minutes</option>
                <option>15 minutes</option>
                <option>1 hour</option>
              </select>
            </SettingRow>
            <SettingRow label="Historical data range" description="Maximum date range for analytics">
              <select className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand">
                <option>90 days</option>
                <option>180 days</option>
                <option>1 year</option>
              </select>
            </SettingRow>
          </SectionCard>
        )}
      </div>
    </div>
  );
}
