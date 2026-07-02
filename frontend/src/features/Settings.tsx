import { useRef, useState, type ChangeEvent } from "react";
import { motion } from "framer-motion";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Globe,
  Bell,
  Palette,
  RefreshCw,
  Save,
  CheckCircle,
  User,
  Upload,
  Trash2,
  Shield,
  KeyRound,
  Building2,
  CreditCard,
  Eye,
  EyeOff,
  Copy,
  Plus,
  Monitor,
  Smartphone,
} from "lucide-react";
import { useUIStore } from "../stores/ui";
import { THEMES, useThemeStore } from "../stores/theme";
import { useAuthStore } from "../stores/auth";
import { useProfileStore } from "../stores/profile";
import { useOrgStore } from "../stores/org";
import Avatar from "../components/Avatar";
import OrgLogo from "../components/OrgLogo";
import PageHeader from "../components/PageHeader";
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

const passwordSchema = z
  .object({
    currentPassword: z.string().min(1, "Current password is required"),
    newPassword: z.string().min(8, "Must be at least 8 characters"),
    confirmPassword: z.string(),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

type PasswordForm = z.infer<typeof passwordSchema>;

const SECTIONS = [
  { id: "profile",       label: "Profile",        icon: User },
  { id: "appearance",    label: "Appearance",     icon: Palette },
  { id: "notifications", label: "Notifications",  icon: Bell },
  { id: "security",      label: "Security",       icon: Shield },
  { id: "api-keys",      label: "API Keys",       icon: KeyRound },
  { id: "organization",  label: "Organization",   icon: Building2 },
  { id: "data",          label: "Data",           icon: RefreshCw },
  { id: "billing",       label: "Billing",        icon: CreditCard },
  { id: "api",           label: "Developer API",  icon: Globe },
];

interface ApiKey {
  id: string;
  name: string;
  key: string;
  created: string;
}

interface Session {
  id: string;
  device: string;
  location: string;
  lastActive: string;
  current: boolean;
  icon: React.ElementType;
}

const INITIAL_SESSIONS: Session[] = [
  { id: "s1", device: "This device", location: "Current session", lastActive: "Active now", current: true, icon: Monitor },
  { id: "s2", device: "iPhone · Safari", location: "Last seen recently", lastActive: "2h ago", current: false, icon: Smartphone },
];

function SectionCard({
  title,
  description,
  icon: Icon,
  actions,
  children,
}: {
  title: string;
  description?: string;
  icon: React.ElementType;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-card-lg border border-border-subtle p-5 relative overflow-hidden"
    >
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h3 className="text-sm font-semibold text-tx-primary flex items-center gap-2">
            <Icon size={14} className="text-tx-muted" />
            {title}
          </h3>
          {description && <p className="text-xs text-tx-muted mt-1">{description}</p>}
        </div>
        {actions}
      </div>
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

function TextField({
  label,
  error,
  ...rest
}: { label: string; error?: string | undefined } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label className="text-xs text-tx-muted block mb-1.5">{label}</label>
      <input
        {...rest}
        className={cn(
          "w-full bg-app-bg border rounded-lg px-3 py-2 text-sm text-tx-primary",
          "placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors",
          error ? "border-danger" : "border-border",
        )}
      />
      {error && <p className="text-danger text-xs mt-1">{error}</p>}
    </div>
  );
}

function generateApiKey(): string {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let out = "ctk_live_";
  for (let i = 0; i < 32; i++) out += chars[Math.floor(Math.random() * chars.length)];
  return out;
}

export default function Settings() {
  const { currency, setCurrency } = useUIStore();
  const { theme, setTheme } = useThemeStore();
  const { user, updateUser } = useAuthStore();
  const { avatarUrl, timezone, language, bio, setAvatar, setTimezone, setLanguage, setBio } = useProfileStore();
  const [active, setActive] = useState("profile");
  const [saved, setSaved] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(300);
  const [notifs, setNotifs] = useState({ budget: true, anomaly: true, weekly: false, marketing: false, security: true });
  const [compactNumbers, setCompactNumbers] = useState(true);
  const [profileSaved, setProfileSaved] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  // Security tab — local-only state; no backend endpoint exists for these yet.
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [sessions, setSessions] = useState<Session[]>(INITIAL_SESSIONS);
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);

  // API Keys tab — local-only mock keys; no backend endpoint exists for these yet.
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});

  // Organization tab — local-only preferences.
  const { organizationId, organizationName, organizationLogos, setOrganizationLogo } = useOrgStore();
  const [orgName, setOrgName] = useState(organizationName || "Acme Corp");
  const [budgetAlerts, setBudgetAlerts] = useState(true);
  const [orgSaved, setOrgSaved] = useState(false);
  const orgLogoInputRef = useRef<HTMLInputElement>(null);
  const orgLogoUrl = organizationId ? organizationLogos[organizationId] : undefined;

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

  function onOrgLogoSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !organizationId) return;
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
      setOrganizationLogo(organizationId, reader.result as string);
      toast.success("Organization logo updated");
    };
    reader.onerror = () => toast.error("Couldn't read that image", "Please try a different file.");
    reader.readAsDataURL(file);
  }

  function removeOrgLogo() {
    if (!organizationId) return;
    setOrganizationLogo(organizationId, null);
    toast.info("Organization logo removed");
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

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    reset: resetPassword,
    formState: { errors: passwordErrors },
  } = useForm<PasswordForm>({
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  function onSavePassword(data: PasswordForm) {
    const result = passwordSchema.safeParse(data);
    if (!result.success) {
      toast.error("Couldn't update password", result.error.issues[0]?.message ?? "Check the fields and try again.");
      return;
    }
    // No backend endpoint for password changes yet — this is intentionally local-only.
    setPasswordSaved(true);
    resetPassword();
    toast.success("Password updated", "This preview doesn't yet persist to the backend.");
    setTimeout(() => setPasswordSaved(false), 2500);
  }

  function revokeSession(id: string) {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    toast.success("Session revoked");
  }

  function createApiKey() {
    const key: ApiKey = {
      id: `${Date.now()}`,
      name: `Key ${apiKeys.length + 1}`,
      key: generateApiKey(),
      created: "Just now",
    };
    setApiKeys((prev) => [key, ...prev]);
    setVisibleKeys((prev) => ({ ...prev, [key.id]: true }));
    toast.success("API key generated", "Copy it now — you won't be able to see it again.");
  }

  function revokeApiKey(id: string) {
    setApiKeys((prev) => prev.filter((k) => k.id !== id));
    toast.info("API key revoked");
  }

  function copyApiKey(key: string) {
    void navigator.clipboard?.writeText(key);
    toast.success("Copied to clipboard");
  }

  function onSaveOrganization() {
    if (organizationId && orgName.trim()) {
      useOrgStore.getState().setOrganization(organizationId, orgName.trim());
    }
    setOrgSaved(true);
    toast.success("Organization preferences saved");
    setTimeout(() => setOrgSaved(false), 2500);
  }

  return (
    <div className="p-4 sm:p-6 max-w-5xl">
      <PageHeader title="Settings" description="Configure your profile, workspace, and account preferences." />

      <div className="flex flex-col lg:flex-row gap-6 mt-6">
        {/* Tab list */}
        <div className="lg:w-52 flex-shrink-0">
          <div className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-visible bg-app-card lg:bg-transparent rounded-lg lg:rounded-none p-1 lg:p-0 border lg:border-0 border-border-subtle">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap flex-shrink-0",
                  active === s.id
                    ? "bg-brand-subtle text-brand"
                    : "text-tx-secondary hover:text-tx-primary hover:bg-app-hover",
                )}
              >
                <s.icon size={15} className="flex-shrink-0" />
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Panel */}
        <div className="min-w-0 flex-1 space-y-5">
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
                  <TextField
                    label="Display name"
                    {...registerProfile("displayName")}
                    error={profileErrors.displayName?.message}
                  />
                  <TextField
                    label="Username"
                    {...registerProfile("username")}
                    error={profileErrors.username?.message}
                  />
                </div>

                <TextField
                  label="Email address"
                  type="email"
                  {...registerProfile("email")}
                  error={profileErrors.email?.message}
                />

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

          {active === "appearance" && (
            <SectionCard title="Appearance" icon={Palette}>
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
                { key: "budget" as const,    label: "Budget alerts",     desc: "Alert when projects exceed 80% budget" },
                { key: "anomaly" as const,   label: "Anomaly detection", desc: "Notify on unusual cost spikes" },
                { key: "weekly" as const,    label: "Weekly digest",     desc: "Weekly cost summary email" },
                { key: "security" as const,  label: "Security events",   desc: "Sign-ins and permission changes" },
                { key: "marketing" as const, label: "Product updates",   desc: "New features and announcements" },
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

          {active === "security" && (
            <>
              <form onSubmit={(e) => { void handlePasswordSubmit(onSavePassword)(e); }}>
                <SectionCard title="Password" icon={Shield}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <TextField
                      label="Current password"
                      type="password"
                      autoComplete="current-password"
                      {...registerPassword("currentPassword")}
                      error={passwordErrors.currentPassword?.message}
                    />
                    <div />
                    <TextField
                      label="New password"
                      type="password"
                      autoComplete="new-password"
                      {...registerPassword("newPassword")}
                      error={passwordErrors.newPassword?.message}
                    />
                    <TextField
                      label="Confirm new password"
                      type="password"
                      autoComplete="new-password"
                      {...registerPassword("confirmPassword")}
                      error={passwordErrors.confirmPassword?.message}
                    />
                  </div>
                  <button
                    type="submit"
                    className={cn("btn-primary w-fit", passwordSaved && "bg-success hover:bg-success")}
                  >
                    {passwordSaved ? <CheckCircle size={14} /> : <Save size={14} />}
                    {passwordSaved ? "Updated!" : "Update password"}
                  </button>
                </SectionCard>
              </form>

              <SectionCard title="Two-factor authentication" description="Add an extra layer of security to your account" icon={Shield}>
                <div className="flex items-center gap-3 rounded-xl border border-dashed border-border p-4">
                  <div className="w-10 h-10 rounded-lg bg-brand-subtle flex items-center justify-center flex-shrink-0">
                    <Shield size={18} className="text-brand" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-tx-primary">
                      {twoFactorEnabled ? "2FA is enabled" : "2FA is not enabled"}
                    </p>
                    <p className="text-xs text-tx-muted">Enable an authenticator app for stronger security</p>
                  </div>
                  <button
                    onClick={() => {
                      setTwoFactorEnabled((v) => !v);
                      toast.success(twoFactorEnabled ? "2FA disabled" : "2FA enabled");
                    }}
                    className={twoFactorEnabled ? "btn-outline h-9 text-xs px-4" : "btn-primary h-9 text-xs px-4"}
                  >
                    {twoFactorEnabled ? "Disable" : "Enable"}
                  </button>
                </div>
              </SectionCard>

              <SectionCard title="Active Sessions" description="Devices currently signed in to your account" icon={Monitor}>
                <ul className="divide-y divide-border-subtle -mt-1">
                  {sessions.map((s) => (
                    <li key={s.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                      <s.icon size={16} className="text-tx-muted flex-shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-tx-primary">{s.device}</p>
                        <p className="text-xs text-tx-muted">{s.location} · {s.lastActive}</p>
                      </div>
                      {s.current ? (
                        <span className="badge bg-success-dim text-success text-[10px]">Current</span>
                      ) : (
                        <button
                          onClick={() => revokeSession(s.id)}
                          className="btn-outline h-7 text-xs px-2.5 text-danger hover:bg-danger-dim hover:border-danger/40"
                        >
                          Revoke
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </SectionCard>
            </>
          )}

          {active === "api-keys" && (
            <SectionCard
              title="API Keys"
              description="Use these to authenticate programmatic access to the Costorah API"
              icon={KeyRound}
              actions={
                <button onClick={createApiKey} className="btn-primary h-8 text-xs px-3">
                  <Plus size={13} />
                  Generate key
                </button>
              }
            >
              {apiKeys.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <div className="w-10 h-10 rounded-xl bg-app-muted flex items-center justify-center mb-3">
                    <KeyRound size={18} className="text-tx-muted" />
                  </div>
                  <p className="text-sm font-medium text-tx-primary mb-1">No API keys yet</p>
                  <p className="text-xs text-tx-muted">Generate one to start calling the Costorah API.</p>
                </div>
              ) : (
                <ul className="divide-y divide-border-subtle -mt-1">
                  {apiKeys.map((k) => (
                    <li key={k.id} className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-tx-primary">{k.name}</p>
                        <div className="mt-1 flex items-center gap-1.5">
                          <code className="rounded-md bg-app-muted px-2 py-1 text-xs font-mono text-tx-secondary">
                            {visibleKeys[k.id] ? k.key : `${k.key.slice(0, 9)}${"•".repeat(16)}`}
                          </code>
                          <button
                            onClick={() => setVisibleKeys((prev) => ({ ...prev, [k.id]: !prev[k.id] }))}
                            aria-label={visibleKeys[k.id] ? "Hide key" : "Show key"}
                            className="btn-ghost h-7 w-7 p-0 justify-center"
                          >
                            {visibleKeys[k.id] ? <EyeOff size={13} /> : <Eye size={13} />}
                          </button>
                          <button
                            onClick={() => copyApiKey(k.key)}
                            aria-label="Copy key"
                            className="btn-ghost h-7 w-7 p-0 justify-center"
                          >
                            <Copy size={13} />
                          </button>
                        </div>
                        <p className="mt-1 text-[11px] text-tx-muted">Created {k.created}</p>
                      </div>
                      <button
                        onClick={() => revokeApiKey(k.id)}
                        className="btn-outline h-8 text-xs px-3 text-danger hover:bg-danger-dim hover:border-danger/40 flex-shrink-0"
                      >
                        <Trash2 size={13} />
                        Revoke
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          )}

          {active === "organization" && (
            <SectionCard title="Organization Preferences" icon={Building2}>
              <div className="flex items-center gap-4">
                <OrgLogo size={64} />
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => orgLogoInputRef.current?.click()}
                      disabled={!organizationId}
                      className="btn-outline h-8 text-xs px-3 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Upload size={13} />
                      {orgLogoUrl ? "Replace logo" : "Upload logo"}
                    </button>
                    {orgLogoUrl && (
                      <button
                        type="button"
                        onClick={removeOrgLogo}
                        aria-label="Remove organization logo"
                        className="btn-ghost h-8 w-8 p-0 justify-center text-danger hover:bg-danger-dim"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-tx-muted">
                    {organizationId ? "PNG, JPG or GIF. Max 2MB." : "Select an organization to set a logo."}
                  </p>
                  <input
                    ref={orgLogoInputRef}
                    type="file"
                    accept="image/*"
                    onChange={onOrgLogoSelected}
                    className="sr-only"
                    aria-label="Upload organization logo"
                  />
                </div>
              </div>

              <TextField label="Organization name" value={orgName} onChange={(e) => setOrgName(e.target.value)} />
              <SettingRow label="Budget alerts" description="Notify admins when org-wide spend approaches budget">
                <Toggle value={budgetAlerts} onChange={setBudgetAlerts} label="Budget alerts" />
              </SettingRow>
              <button
                onClick={onSaveOrganization}
                className={cn("btn-primary w-fit", orgSaved && "bg-success hover:bg-success")}
              >
                {orgSaved ? <CheckCircle size={14} /> : <Save size={14} />}
                {orgSaved ? "Saved!" : "Save preferences"}
              </button>
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

          {active === "billing" && (
            <>
              <SectionCard title="Current Plan" icon={CreditCard}>
                <div className="flex flex-col gap-4 rounded-xl bg-gradient-brand p-5 text-app-bg md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-widest opacity-80">Current plan</p>
                    <p className="mt-1 font-display text-2xl font-bold">Enterprise</p>
                    <p className="mt-1 text-sm opacity-90">Unlimited projects · Priority support</p>
                  </div>
                  <button className="h-10 rounded-lg bg-app-bg/20 px-4 text-sm font-semibold backdrop-blur hover:bg-app-bg/30 flex-shrink-0">
                    Manage subscription
                  </button>
                </div>
              </SectionCard>
              <SectionCard title="Payment Method" icon={CreditCard}>
                <div className="flex items-center gap-4 rounded-xl border border-border-subtle bg-app-bg p-4">
                  <div className="grid h-10 w-14 place-items-center rounded-md bg-tx-primary text-xs font-bold text-app-bg flex-shrink-0">
                    VISA
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-tx-primary">•••• •••• •••• 4242</p>
                    <p className="text-xs text-tx-muted">Expires 08/28</p>
                  </div>
                  <button className="btn-outline h-8 text-xs px-3 flex-shrink-0">Update</button>
                </div>
                <p className="text-xs text-tx-muted">Billing is a preview — connect a payment provider to enable this.</p>
              </SectionCard>
            </>
          )}

          {active === "api" && (
            <form onSubmit={(e) => { void handleSubmit(onSave)(e); }}>
              <SectionCard title="Developer API Configuration" icon={Globe}>
                <TextField
                  label="Backend URL"
                  {...register("apiBaseUrl")}
                  error={errors.apiBaseUrl?.message}
                  placeholder="http://localhost:8000"
                />
                <TextField
                  label="Request Timeout (ms)"
                  type="number"
                  {...register("timeout", { valueAsNumber: true })}
                  error={errors.timeout?.message}
                />
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
        </div>
      </div>
    </div>
  );
}
