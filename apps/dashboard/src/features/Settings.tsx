import { forwardRef, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Building2,
  CheckCircle,
  KeyRound,
  Loader2,
  Palette,
  Save,
  Shield,
  Trash2,
  Triangle,
  User,
} from "lucide-react";
import { useUIStore } from "../stores/ui";
import { THEMES, useThemeStore } from "../stores/theme";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { ApiKeysManager } from "./ApiKeys";
import PageHeader from "../components/PageHeader";
import Avatar from "../components/Avatar";
import ConfirmDialog from "../components/ConfirmDialog";
import { cn, formatDateTime } from "../utils";
import { toast } from "../stores/toast";
import {
  ApiError,
  changePassword,
  deleteAccount,
  deleteOrganization,
  getOrganizations,
  updateOrganization,
  updatePreferences,
  updateProfile,
} from "../services/api";
import type { Currency } from "../types/api";

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

const DATE_FORMATS = [
  { value: "MM/DD/YYYY", label: "MM/DD/YYYY (US)" },
  { value: "DD/MM/YYYY", label: "DD/MM/YYYY (EU)" },
  { value: "YYYY-MM-DD", label: "YYYY-MM-DD (ISO)" },
];

const profileSchema = z.object({
  displayName: z.string().min(1, "Display name is required").max(255),
  username: z
    .string()
    .max(50)
    .regex(/^[a-zA-Z0-9_.-]*$/, "Only letters, numbers, . _ - allowed"),
  avatarUrl: z.string().max(2048),
  bio: z.string().max(2000, "Keep it under 2000 characters"),
});
type ProfileForm = z.infer<typeof profileSchema>;

const workspaceSchema = z.object({
  name: z.string().min(1, "Workspace name is required").max(255),
  description: z.string().max(10000),
});
type WorkspaceForm = z.infer<typeof workspaceSchema>;

const passwordSchema = z
  .object({
    currentPassword: z.string().min(1, "Current password is required"),
    newPassword: z.string().min(8, "Must be at least 8 characters").max(128),
    confirmPassword: z.string(),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });
type PasswordForm = z.infer<typeof passwordSchema>;

const SECTIONS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "workspace", label: "Workspace", icon: Building2 },
  { id: "password", label: "Password", icon: Shield },
  { id: "preferences", label: "Preferences", icon: Palette },
  { id: "api-keys", label: "API Keys", icon: KeyRound },
  { id: "danger", label: "Danger Zone", icon: Triangle },
] as const;

function apiErrorMessage(err: unknown, fallback: string): { title: string; description: string } {
  if (err instanceof ApiError) {
    if (err.status === 401) return { title: "Incorrect password", description: err.message };
    if (err.status === 409) return { title: "Not allowed", description: err.message };
    if (err.status === 400) return { title: "Not allowed", description: err.message };
    if (err.status === 403) {
      return { title: "Not allowed", description: "You don't have permission to do that." };
    }
    if (err.status === 422) return { title: "Invalid request", description: err.message };
  }
  return { title: "Something went wrong", description: fallback };
}

function SectionCard({
  title,
  description,
  icon: Icon,
  actions,
  children,
  danger = false,
}: {
  title: string;
  description?: string;
  icon: React.ElementType;
  actions?: React.ReactNode;
  children: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "glass-card rounded-card-lg border p-5 relative overflow-hidden",
        danger ? "border-danger/30" : "border-border-subtle",
      )}
    >
      <div
        className={cn(
          "absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent to-transparent",
          danger ? "via-danger/50" : "via-brand/40",
        )}
        aria-hidden="true"
      />
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h3
            className={cn(
              "text-sm font-semibold flex items-center gap-2",
              danger ? "text-danger" : "text-tx-primary",
            )}
          >
            <Icon size={14} className={danger ? "text-danger" : "text-tx-muted"} />
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

const TextField = forwardRef<
  HTMLInputElement,
  { label: string; error?: string | undefined } & React.InputHTMLAttributes<HTMLInputElement>
>(function TextField({ label, error, id, ...rest }, ref) {
  const fieldId = id ?? `field-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div>
      <label htmlFor={fieldId} className="text-xs text-tx-muted block mb-1.5">{label}</label>
      <input
        ref={ref}
        id={fieldId}
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
});

/** Read a preference key with a typed fallback — the preferences bag is a free-form JSON blob. */
function pref<T>(preferences: Record<string, unknown> | undefined, key: string, fallback: T): T {
  const v = preferences?.[key];
  return v === undefined ? fallback : (v as T);
}

export default function Settings() {
  const queryClient = useQueryClient();
  const { currency, setCurrency } = useUIStore();
  const { theme, setTheme } = useThemeStore();
  const { sidebarCollapsed, setSidebarCollapsed } = useUIStore();
  const { user, updateUser, clearAuth } = useAuthStore();
  const { organizationId, organizationName, setOrganization, clearOrganization } = useOrgStore();
  const [active, setActive] = useState<(typeof SECTIONS)[number]["id"]>("profile");

  const preferences = user?.preferences ?? {};

  // ── Profile ────────────────────────────────────────────────────────────────

  const [profileSaved, setProfileSaved] = useState(false);
  const {
    register: registerProfile,
    handleSubmit: handleProfileSubmit,
    reset: resetProfileForm,
    formState: { errors: profileErrors },
  } = useForm<ProfileForm>({
    defaultValues: {
      displayName: user?.display_name ?? "",
      username: user?.username ?? "",
      avatarUrl: user?.avatar_url ?? "",
      bio: user?.bio ?? "",
    },
  });

  useEffect(() => {
    resetProfileForm({
      displayName: user?.display_name ?? "",
      username: user?.username ?? "",
      avatarUrl: user?.avatar_url ?? "",
      bio: user?.bio ?? "",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const profileMutation = useMutation({
    mutationFn: (data: ProfileForm) =>
      updateProfile({
        display_name: data.displayName,
        username: data.username || null,
        avatar_url: data.avatarUrl || null,
        bio: data.bio || null,
      }),
    onSuccess: (updated) => {
      updateUser({
        display_name: updated.display_name,
        username: updated.username,
        avatar_url: updated.avatar_url,
        bio: updated.bio,
        timezone: updated.timezone,
      });
      setProfileSaved(true);
      toast.success("Profile updated");
      setTimeout(() => setProfileSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not save your profile. Please try again.");
      toast.error(title, description);
    },
  });

  function onSaveProfile(data: ProfileForm) {
    const result = profileSchema.safeParse(data);
    if (!result.success) {
      toast.error("Couldn't save profile", result.error.issues[0]?.message ?? "Fix the highlighted fields.");
      return;
    }
    profileMutation.mutate(result.data);
  }

  // ── Workspace ──────────────────────────────────────────────────────────────

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });
  const currentOrg = orgsQuery.data?.organizations.find((o) => o.id === organizationId);

  const [workspaceSaved, setWorkspaceSaved] = useState(false);
  const {
    register: registerWorkspace,
    handleSubmit: handleWorkspaceSubmit,
    reset: resetWorkspaceForm,
  } = useForm<WorkspaceForm>({
    defaultValues: { name: currentOrg?.name ?? "", description: currentOrg?.description ?? "" },
  });

  useEffect(() => {
    if (currentOrg) {
      resetWorkspaceForm({ name: currentOrg.name, description: currentOrg.description ?? "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentOrg?.id]);

  const workspaceMutation = useMutation({
    mutationFn: (data: WorkspaceForm) =>
      updateOrganization(organizationId!, { name: data.name, description: data.description }),
    onSuccess: (updated) => {
      setOrganization(updated.id, updated.name);
      void orgsQuery.refetch();
      setWorkspaceSaved(true);
      toast.success("Workspace updated");
      setTimeout(() => setWorkspaceSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not save workspace settings. Please try again.");
      toast.error(title, description);
    },
  });

  function onSaveWorkspace(data: WorkspaceForm) {
    const result = workspaceSchema.safeParse(data);
    if (!result.success) {
      toast.error("Couldn't save workspace", result.error.issues[0]?.message ?? "Fix the highlighted fields.");
      return;
    }
    if (!organizationId) return;
    workspaceMutation.mutate(result.data);
  }

  // ── Password ───────────────────────────────────────────────────────────────

  const [passwordSaved, setPasswordSaved] = useState(false);
  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    reset: resetPassword,
    formState: { errors: passwordErrors },
  } = useForm<PasswordForm>({
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  const passwordMutation = useMutation({
    mutationFn: (data: PasswordForm) => changePassword(data.currentPassword, data.newPassword),
    onSuccess: () => {
      setPasswordSaved(true);
      resetPassword();
      toast.success("Password updated", "You're still signed in here — every other session was signed out.");
      setTimeout(() => setPasswordSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not update your password. Please try again.");
      toast.error(title, description);
    },
  });

  function onSavePassword(data: PasswordForm) {
    const result = passwordSchema.safeParse(data);
    if (!result.success) {
      toast.error("Couldn't update password", result.error.issues[0]?.message ?? "Check the fields and try again.");
      return;
    }
    passwordMutation.mutate(result.data);
  }

  // ── Preferences ────────────────────────────────────────────────────────────

  const preferencesMutation = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updatePreferences(patch),
    onSuccess: (updated) => {
      updateUser({ preferences: updated.preferences });
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not save this preference. Please try again.");
      toast.error(title, description);
    },
  });

  function savePreference(key: string, value: unknown) {
    preferencesMutation.mutate({ [key]: value });
  }

  function onChangeTimezone(tz: string) {
    savePreference("timezone", tz);
    toast.success("Timezone saved");
  }

  function onChangeDateFormat(fmt: string) {
    savePreference("date_format", fmt);
    toast.success("Date format saved");
  }

  function onChangeCurrency(c: Currency) {
    setCurrency(c);
    savePreference("currency", c);
  }

  function onChangeTheme(t: (typeof THEMES)[number]["id"]) {
    setTheme(t);
    savePreference("theme", t);
  }

  function onToggleSidebar(collapsed: boolean) {
    setSidebarCollapsed(collapsed);
    savePreference("sidebar_collapsed", collapsed);
  }

  const NOTIFICATION_DEFAULTS: Record<string, boolean> = {
    budget: true,
    anomaly: true,
    weekly: false,
    security: true,
  };
  const notificationPrefs = pref<Record<string, boolean>>(
    preferences,
    "notifications",
    NOTIFICATION_DEFAULTS,
  );

  function onToggleNotification(key: string, value: boolean) {
    savePreference("notifications", { ...notificationPrefs, [key]: value });
  }

  // ── Danger Zone ────────────────────────────────────────────────────────────

  const [deleteWorkspaceOpen, setDeleteWorkspaceOpen] = useState(false);
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("");

  const deleteWorkspaceMutation = useMutation({
    mutationFn: () => deleteOrganization(organizationId!),
    onSuccess: () => {
      toast.success("Workspace deleted");
      clearOrganization();
      setDeleteWorkspaceOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not delete this workspace. Please try again.");
      toast.error(title, description);
      setDeleteWorkspaceOpen(false);
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: () => deleteAccount(deleteAccountPassword),
    onSuccess: () => {
      toast.success("Account deleted");
      clearAuth();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not delete your account. Please try again.");
      toast.error(title, description);
    },
  });

  const displayName = user?.display_name ?? "";

  return (
    <div className="p-4 sm:p-6 max-w-5xl">
      <PageHeader title="Settings" description="Manage your profile, workspace, and account preferences." />

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
                    ? s.id === "danger"
                      ? "bg-danger-dim text-danger"
                      : "bg-brand-subtle text-brand"
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
                  <div>
                    <p className="text-sm font-medium text-tx-primary">{displayName}</p>
                    <p className="text-xs text-tx-muted">{user?.email}</p>
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
                  label="Avatar URL"
                  placeholder="https://example.com/avatar.png"
                  {...registerProfile("avatarUrl")}
                  error={profileErrors.avatarUrl?.message}
                />

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-tx-muted block mb-1.5">Email address</label>
                    <input
                      readOnly
                      value={user?.email ?? ""}
                      className="w-full bg-app-muted border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-muted cursor-not-allowed"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-tx-muted block mb-1.5">Account status</label>
                    <input
                      readOnly
                      value={user?.status ?? ""}
                      className="w-full bg-app-muted border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-muted cursor-not-allowed capitalize"
                    />
                  </div>
                </div>

                {user?.created_at && (
                  <div>
                    <label className="text-xs text-tx-muted block mb-1.5">Member since</label>
                    <input
                      readOnly
                      value={formatDateTime(user.created_at)}
                      className="w-full bg-app-muted border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-muted cursor-not-allowed"
                    />
                  </div>
                )}

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
                  disabled={profileMutation.isPending}
                  className={cn("btn-primary w-fit", profileSaved && "bg-success hover:bg-success")}
                >
                  {profileMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : profileSaved ? (
                    <CheckCircle size={14} />
                  ) : (
                    <Save size={14} />
                  )}
                  {profileSaved ? "Saved!" : "Save Changes"}
                </button>
              </SectionCard>
            </form>
          )}

          {active === "workspace" && (
            <form onSubmit={(e) => { void handleWorkspaceSubmit(onSaveWorkspace)(e); }}>
              <SectionCard title="Workspace" icon={Building2}>
                {orgsQuery.isLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }, (_, i) => <div key={i} className="h-9 skeleton rounded-lg" />)}
                  </div>
                ) : !currentOrg ? (
                  <p className="text-xs text-tx-muted">Select a workspace to manage its settings.</p>
                ) : (
                  <>
                    <TextField label="Workspace name" {...registerWorkspace("name")} />
                    <div>
                      <label htmlFor="ws-description" className="text-xs text-tx-muted block mb-1.5">
                        Description (optional)
                      </label>
                      <textarea
                        id="ws-description"
                        rows={3}
                        {...registerWorkspace("description")}
                        placeholder="What is this workspace for?"
                        className="w-full bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary resize-none placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors"
                      />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs text-tx-muted block mb-1.5">Slug</label>
                        <input
                          readOnly
                          value={currentOrg.slug}
                          className="w-full bg-app-muted border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-muted cursor-not-allowed font-mono"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-tx-muted block mb-1.5">Organization ID</label>
                        <input
                          readOnly
                          value={currentOrg.id}
                          className="w-full bg-app-muted border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-muted cursor-not-allowed font-mono truncate"
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {currentOrg.is_personal && (
                        <span className="badge bg-brand-subtle text-brand text-[10px] uppercase tracking-wide">
                          Personal workspace
                        </span>
                      )}
                      {currentOrg.created_at && (
                        <span className="text-xs text-tx-muted">
                          Created {formatDateTime(currentOrg.created_at)}
                        </span>
                      )}
                    </div>
                    <button
                      type="submit"
                      disabled={workspaceMutation.isPending}
                      className={cn("btn-primary w-fit", workspaceSaved && "bg-success hover:bg-success")}
                    >
                      {workspaceMutation.isPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : workspaceSaved ? (
                        <CheckCircle size={14} />
                      ) : (
                        <Save size={14} />
                      )}
                      {workspaceSaved ? "Saved!" : "Save Changes"}
                    </button>
                  </>
                )}
              </SectionCard>
            </form>
          )}

          {active === "password" && (
            <form onSubmit={(e) => { void handlePasswordSubmit(onSavePassword)(e); }}>
              <SectionCard title="Password" icon={Shield} description="Changing your password signs out every other session.">
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
                  disabled={passwordMutation.isPending}
                  className={cn("btn-primary w-fit", passwordSaved && "bg-success hover:bg-success")}
                >
                  {passwordMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : passwordSaved ? (
                    <CheckCircle size={14} />
                  ) : (
                    <Save size={14} />
                  )}
                  {passwordSaved ? "Updated!" : "Update password"}
                </button>
              </SectionCard>
            </form>
          )}

          {active === "preferences" && (
            <>
              <SectionCard title="Appearance" icon={Palette}>
                <SettingRow label="Theme" description="Neon Cyber, Professional Light, or Professional Dark">
                  <div className="flex gap-1 bg-app-bg rounded-lg p-0.5 border border-border-subtle">
                    {THEMES.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => onChangeTheme(t.id)}
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
                    onChange={(e) => onChangeCurrency(e.target.value as Currency)}
                    className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
                  >
                    {["USD", "EUR", "GBP"].map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </SettingRow>
                <SettingRow label="Collapse sidebar" description="Start with the sidebar collapsed">
                  <Toggle value={sidebarCollapsed} onChange={onToggleSidebar} label="Collapse sidebar" />
                </SettingRow>
              </SectionCard>

              <SectionCard title="Regional" icon={Palette}>
                <SettingRow label="Timezone" description="Used to display dates and times">
                  <select
                    value={pref(preferences, "timezone", "UTC")}
                    onChange={(e) => onChangeTimezone(e.target.value)}
                    className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
                  >
                    {(TIMEZONES.includes(pref(preferences, "timezone", "UTC"))
                      ? TIMEZONES
                      : [pref(preferences, "timezone", "UTC"), ...TIMEZONES]
                    ).map((tz) => (
                      <option key={tz} value={tz}>{tz}</option>
                    ))}
                  </select>
                </SettingRow>
                <SettingRow label="Date format" description="How dates are displayed across the dashboard">
                  <select
                    value={pref(preferences, "date_format", "MM/DD/YYYY")}
                    onChange={(e) => onChangeDateFormat(e.target.value)}
                    className="bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
                  >
                    {DATE_FORMATS.map((f) => (
                      <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                  </select>
                </SettingRow>
              </SectionCard>

              <SectionCard title="Notification Preferences" icon={Bell}>
                {[
                  { key: "budget", label: "Budget alerts", desc: "Alert when projects exceed 80% budget" },
                  { key: "anomaly", label: "Anomaly detection", desc: "Notify on unusual cost spikes" },
                  { key: "weekly", label: "Weekly digest", desc: "Weekly cost summary email" },
                  { key: "security", label: "Security events", desc: "Sign-ins and permission changes" },
                ].map((n) => (
                  <SettingRow key={n.key} label={n.label} description={n.desc}>
                    <Toggle
                      value={notificationPrefs[n.key] ?? false}
                      onChange={(v) => onToggleNotification(n.key, v)}
                      label={n.label}
                    />
                  </SettingRow>
                ))}
              </SectionCard>
            </>
          )}

          {active === "api-keys" && (
            <SectionCard title="API Keys" icon={KeyRound} description="Programmatic access to your organization's data.">
              <ApiKeysManager compact />
            </SectionCard>
          )}

          {active === "danger" && (
            <>
              <SectionCard
                title="Delete Workspace"
                icon={Triangle}
                danger
                description="Permanently delete this workspace and everything in it. This cannot be undone."
              >
                {currentOrg?.is_personal ? (
                  <p className="text-xs text-tx-muted">
                    Your personal workspace can't be deleted — it's required by your account.
                  </p>
                ) : (
                  <button
                    onClick={() => setDeleteWorkspaceOpen(true)}
                    disabled={!organizationId}
                    className="h-9 text-xs px-3.5 rounded-lg font-semibold flex items-center gap-1.5 bg-danger text-white hover:bg-danger-light disabled:opacity-50 w-fit"
                  >
                    <Trash2 size={13} />
                    Delete workspace
                  </button>
                )}
              </SectionCard>

              <SectionCard
                title="Delete Account"
                icon={Triangle}
                danger
                description="Permanently delete your account and any workspace you solely own. This cannot be undone."
              >
                <button
                  onClick={() => setDeleteAccountOpen(true)}
                  className="h-9 text-xs px-3.5 rounded-lg font-semibold flex items-center gap-1.5 bg-danger text-white hover:bg-danger-light w-fit"
                >
                  <Trash2 size={13} />
                  Delete account
                </button>
              </SectionCard>
            </>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={deleteWorkspaceOpen}
        title={`Delete "${organizationName ?? "this workspace"}"?`}
        description="This permanently deletes the workspace and all its data — projects, connections, API keys, and members. This cannot be undone."
        confirmLabel="Delete workspace"
        loading={deleteWorkspaceMutation.isPending}
        onConfirm={() => deleteWorkspaceMutation.mutate()}
        onCancel={() => setDeleteWorkspaceOpen(false)}
      />

      <ConfirmDialog
        open={deleteAccountOpen}
        title="Delete your account?"
        description="This permanently deletes your account and any workspace you solely own. Type your password to confirm — this cannot be undone."
        confirmLabel={deleteAccountMutation.isPending ? "Deleting..." : "Delete account"}
        loading={deleteAccountMutation.isPending}
        onConfirm={() => {
          if (!deleteAccountPassword) {
            toast.error("Password required", "Enter your password to confirm account deletion.");
            return;
          }
          deleteAccountMutation.mutate();
        }}
        onCancel={() => {
          setDeleteAccountOpen(false);
          setDeleteAccountPassword("");
        }}
      >
        <input
          type="password"
          autoComplete="current-password"
          placeholder="Your password"
          value={deleteAccountPassword}
          onChange={(e) => setDeleteAccountPassword(e.target.value)}
          className="w-full bg-app-bg border border-border rounded-lg px-3 py-2 text-sm text-tx-primary placeholder:text-tx-muted focus:outline-none focus:border-danger mt-3"
        />
      </ConfirmDialog>
    </div>
  );
}
