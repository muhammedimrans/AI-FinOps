import { useRef, useState, type ChangeEvent } from "react";
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
  User,
  Upload,
  Trash2,
} from "lucide-react";
import { useUIStore } from "../stores/ui";
import { THEMES, useThemeStore } from "../stores/theme";
import { useAuthStore } from "../stores/auth";
import { useProfileStore } from "../stores/profile";
import Avatar from "../components/Avatar";
import { cn } from "../utils";
import { toast } from "../stores/toast";
import type { Currency } from "../types/api";

const MAX_AVATAR_BYTES = 2 * 1024 * 1024; // 2MB

const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "pt", label: "Português" },
  { code: "ja", label: "日本語" },
];

const profileSchema = z.object({
  displayName: z.string().min(1, "Display name is required").max(80),
  username: z.string().max(40).regex(/^[a-zA-Z0-9_.-]*$/, "Only letters, numbers, . _ - allowed"),
  email: z.string().email("Must be a valid email address"),
  bio: z.string().max(280, "Keep it under 280 characters"),
});

type ProfileForm = z.infer<typeof profileSchema>;

const apiSchema = z.object({
  apiBaseUrl: z.string().url("Must be a valid URL"),
  timeout: z.number().min(1000).max(30000),
});

type ApiForm = z.infer<typeof apiSchema>;

const SECTIONS = [
  { id: "profile",       label: "Profile",       icon: User },
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
      className="glass-card rounded-card-lg border border-border-subtle p-5 relative overflow-hidden"
    >
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />
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

function Toggle({
  value,
  onChange,
  label,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={cn(
        "relative w-10 h-5.5 rounded-full border transition-colors duration-base flex-shrink-0",
        value ? "bg-brand border-brand" : "bg-app-muted border-border",
      )}
      aria-checked={value}
      aria-label={label}
      role="switch"
    >
      <span
        className={cn(
          "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-md transition-transform duration-base",
          value ? "translate-x-5" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

export default function Settings() {
  const { currency, setCurrency } = useUIStore();
  const { theme, setTheme } = useThemeStore();
  const { user, updateUser } = useAuthStore();
  const { avatarUrl, timezone, language, bio, setAvatar, setTimezone, setLanguage, setBio } = useProfileStore();
  const [active, setActive] = useState("profile");
  const [saved, setSaved] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(300);
  const [notifs, setNotifs] = useState({ budget: true, anomaly: true, weekly: false, marketing: false });
  const [compactNumbers, setCompactNumbers] = useState(true);
  const [profileSaved, setProfileSaved] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  const displayName = user?.display_name ?? "";

  const {
    register: registerProfile,
    handleSubmit: handleProfileSubmit,
    setError: setProfileError,
    formState: { errors: profileErrors },
  } = useForm<ProfileForm>({
    defaultValues: {
      displayName,
      username: user?.username ?? "",
      email: user?.email ?? "",
      bio,
    },
  });

  function onAvatarSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error("Invalid file", "Please choose an image file.");
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      toast.error("Image too large", "Please choose an image under 2MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setAvatar(reader.result as string);
      toast.success("Profile photo updated");
    };
    reader.onerror = () => toast.error("Couldn't read that image", "Please try a different file.");
    reader.readAsDataURL(file);
  }

  function removeAvatar() {
    setAvatar(null);
    toast.info("Profile photo removed");
  }

  function onSaveProfile(data: ProfileForm) {
    const result = profileSchema.safeParse(data);
    if (!result.success) {
      for (const issue of result.error.issues) {
        const field = issue.path[0];
        if (field === "displayName" || field === "username" || field === "email" || field === "bio") {
          setProfileError(field, { message: issue.message });
        }
      }
      toast.error("Couldn't save profile", "Fix the highlighted fields and try again.");
      return;
    }
    updateUser({
      display_name: result.data.displayName,
      username: result.data.username || null,
      email: result.data.email,
    });
    setBio(result.data.bio);
    setProfileSaved(true);
    toast.success("Profile updated");
    setTimeout(() => setProfileSaved(false), 2500);
  }

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
      toast.error("Couldn't save settings", "Fix the highlighted fields and try again.");
      return;
    }
    console.info("Settings saved", result.data);
    setSaved(true);
    toast.success("API settings saved");
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
        {active === "profile" && (
          <form onSubmit={(e) => { void handleProfileSubmit(onSaveProfile)(e); }}>
            <SectionCard title="Profile" icon={User}>
              <div className="flex items-center gap-4">
                <Avatar name={displayName || "Account"} size={64} />
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => avatarInputRef.current?.click()}
                      className="btn-outline h-8 text-xs px-3"
                    >
                      <Upload size={13} />
                      {avatarUrl ? "Replace photo" : "Upload photo"}
                    </button>
                    {avatarUrl && (
                      <button
                        type="button"
                        onClick={removeAvatar}
                        aria-label="Remove profile photo"
                        className="btn-ghost h-8 w-8 p-0 justify-center text-danger hover:bg-danger-dim"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-tx-muted">JPG, PNG or GIF. Max 2MB.</p>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/*"
                    onChange={onAvatarSelected}
                    className="sr-only"
                    aria-label="Upload profile photo"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="displayName" className="text-xs text-tx-muted block mb-1.5">Display name</label>
                  <input
                    id="displayName"
                    {...registerProfile("displayName")}
                    className={cn(
                      "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary",
                      "placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors",
                      profileErrors.displayName ? "border-danger" : "border-border",
                    )}
                  />
                  {profileErrors.displayName && (
                    <p className="text-danger text-xs mt-1">{profileErrors.displayName.message}</p>
                  )}
                </div>
                <div>
                  <label htmlFor="username" className="text-xs text-tx-muted block mb-1.5">Username</label>
                  <input
                    id="username"
                    {...registerProfile("username")}
                    className={cn(
                      "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary",
                      "placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors",
                      profileErrors.username ? "border-danger" : "border-border",
                    )}
                  />
                  {profileErrors.username && (
                    <p className="text-danger text-xs mt-1">{profileErrors.username.message}</p>
                  )}
                </div>
              </div>

              <div>
                <label htmlFor="email" className="text-xs text-tx-muted block mb-1.5">Email address</label>
                <input
                  id="email"
                  type="email"
                  {...registerProfile("email")}
                  className={cn(
                    "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary",
                    "placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors",
                    profileErrors.email ? "border-danger" : "border-border",
                  )}
                />
                {profileErrors.email && (
                  <p className="text-danger text-xs mt-1">{profileErrors.email.message}</p>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="timezone" className="text-xs text-tx-muted block mb-1.5">Timezone</label>
                  <select
                    id="timezone"
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
                  >
                    {(TIMEZONES.includes(timezone) ? TIMEZONES : [timezone, ...TIMEZONES]).map((tz) => (
                      <option key={tz} value={tz}>{tz}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="language" className="text-xs text-tx-muted block mb-1.5">Language</label>
                  <select
                    id="language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="w-full bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
                  >
                    {LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor="bio" className="text-xs text-tx-muted block mb-1.5">Bio (optional)</label>
                <textarea
                  id="bio"
                  rows={3}
                  {...registerProfile("bio")}
                  placeholder="Tell us a little about yourself"
                  className={cn(
                    "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary resize-none",
                    "placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors",
                    profileErrors.bio ? "border-danger" : "border-border",
                  )}
                />
                {profileErrors.bio && (
                  <p className="text-danger text-xs mt-1">{profileErrors.bio.message}</p>
                )}
              </div>

              <button
                type="submit"
                className={cn("btn-primary w-fit", profileSaved && "bg-success hover:bg-success")}
              >
                {profileSaved ? <CheckCircle size={14} /> : <Save size={14} />}
                {profileSaved ? "Saved!" : "Save Profile"}
              </button>
            </SectionCard>
          </form>
        )}

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
            <SettingRow label="Theme" description="Neon Cyber, Professional Light, or Professional Dark">
              <div className="flex gap-1 bg-app-bg rounded-lg p-0.5 border border-border-subtle">
                {THEMES.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTheme(t.id)}
                    aria-pressed={theme === t.id}
                    className={cn(
                      "px-3 py-1 rounded-md text-xs font-medium transition-all whitespace-nowrap",
                      theme === t.id ? "bg-brand text-app-bg" : "text-tx-muted hover:text-tx-secondary",
                    )}
                  >
                    {t.label}
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
              <Toggle value={compactNumbers} onChange={setCompactNumbers} label="Compact numbers" />
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
                  label={n.label}
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
