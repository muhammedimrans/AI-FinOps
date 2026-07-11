import { forwardRef, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Building2,
  CheckCircle,
  Clock,
  KeyRound,
  Link2,
  Loader2,
  Mail,
  MailCheck,
  Palette,
  Rocket,
  RotateCcw,
  Save,
  Shield,
  Timer,
  Trash2,
  Triangle,
  Unlink,
  User,
} from "lucide-react";
import { useUIStore } from "../stores/ui";
import { THEMES, useThemeStore } from "../stores/theme";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { useOnboardingWidgetStore } from "../stores/onboardingWidget";
import { ApiKeysManager } from "./ApiKeys";
import PageHeader from "../components/PageHeader";
import Avatar from "../components/Avatar";
import ConfirmDialog from "../components/ConfirmDialog";
import GoogleGlyph from "../components/GoogleGlyph";
import { cn, formatDateTime, typeToConfirmMatches } from "../utils";
import { toast } from "../stores/toast";
import {
  ApiError,
  changePassword,
  deleteAccount,
  deleteOrganization,
  getMe,
  getOrganizations,
  getSchedulerStatus,
  listAlerts,
  listApiKeys,
  listBudgets,
  listInvitations,
  listMembers,
  listProjectsCrud,
  listProviderConnections,
  resendVerification,
  startGoogleLink,
  unlinkGoogle,
  updateOrganization,
  updatePreferences,
  updateProfile,
  updateSchedulerSettings,
  upgradeToBusiness,
  type SchedulerInterval,
} from "../services/api";
import TypeToConfirmField from "../components/TypeToConfirmField";
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
        "glass-card relative overflow-hidden rounded-card-lg border p-5",
        danger ? "border-danger/30" : "border-border-subtle",
      )}
    >
      <div
        className={cn(
          "absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent to-transparent",
          danger ? "via-danger/50" : "via-brand/40",
        )}
        aria-hidden="true"
      />
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3
            className={cn(
              "flex items-center gap-2 text-sm font-semibold",
              danger ? "text-danger" : "text-tx-primary",
            )}
          >
            <Icon size={14} className={danger ? "text-danger" : "text-tx-muted"} />
            {title}
          </h3>
          {description && <p className="mt-1 text-xs text-tx-muted">{description}</p>}
        </div>
        {actions}
      </div>
      <div className="space-y-5">{children}</div>
    </motion.div>
  );
}

/**
 * EP-24.5 Part 7 — "Linked accounts": Google connected email, last login
 * provider, Link/Unlink actions. A separate SectionCard from Profile (not
 * nested in its form) since Link/Unlink are their own top-level-navigation
 * / mutation flows, not part of the profile-save submit.
 */
/**
 * Personal -> Business upgrade (EP-25.2). Only rendered when the caller's
 * current workspace is personal — see the Profile-tab call site. Reuses
 * the existing Organization row (`useOrgStore().setOrganization` + a
 * refetch of the same `["organizations"]` query `updateOrganization`
 * already invalidates elsewhere in this file) so every consumer of
 * `is_personal` (nav, org selector, this page's own Workspace tab) picks
 * up the change immediately — no logout, no reload.
 */
function UpgradeToBusinessCard({ onUpgraded }: { onUpgraded: () => void }) {
  const { setOrganization } = useOrgStore();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const upgradeMutation = useMutation({
    mutationFn: () => upgradeToBusiness(name.trim() || undefined),
    onSuccess: (workspace) => {
      setOrganization(workspace.id, workspace.name, workspace.is_personal);
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
      toast.success(
        "Upgraded to Business",
        `"${workspace.name}" now supports members, invitations, and workspace settings.`,
      );
      onUpgraded();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not upgrade to Business. Please try again.",
      );
      toast.error(title, description);
    },
  });

  return (
    <SectionCard
      title="Upgrade to Business"
      icon={Rocket}
      description="Add teammates, roles, and shared workspace settings — your projects, providers, budgets, alerts, and API keys all carry over exactly as they are."
    >
      <TextField
        label="Workspace name (optional)"
        placeholder="My Team"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <button
        type="button"
        onClick={() => upgradeMutation.mutate()}
        disabled={upgradeMutation.isPending}
        className="btn-primary w-fit"
      >
        {upgradeMutation.isPending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Rocket size={14} />
        )}
        Upgrade to Business
      </button>
    </SectionCard>
  );
}

/**
 * Everything a workspace deletion will take with it (EP-25.3, Part 4).
 * Fetched only while the delete-workspace dialog is open — each list call
 * reuses the exact same paginated endpoint its own management page already
 * calls (Projects/Budgets/Members/API Keys/Alerts/Invitations/Connections),
 * never a bespoke "count everything" endpoint.
 */
function WorkspaceImpactSummary({ organizationId }: { organizationId: string }) {
  const projects = useQuery({
    queryKey: ["projects-crud", organizationId],
    queryFn: () => listProjectsCrud(organizationId),
  });
  const budgets = useQuery({
    queryKey: ["budgets", organizationId],
    queryFn: () => listBudgets(organizationId),
  });
  const members = useQuery({
    queryKey: ["members", organizationId],
    queryFn: () => listMembers(organizationId),
  });
  const apiKeys = useQuery({
    queryKey: ["api-keys", organizationId],
    queryFn: () => listApiKeys(organizationId),
  });
  const alerts = useQuery({
    queryKey: ["alerts", organizationId, "impact-summary"],
    queryFn: () => listAlerts({ organizationId, status: "open", limit: 200 }),
  });
  const invitations = useQuery({
    queryKey: ["invitations", organizationId],
    queryFn: () => listInvitations(organizationId),
  });
  const connections = useQuery({
    queryKey: ["provider-connections", organizationId],
    queryFn: () => listProviderConnections(organizationId),
  });

  const rows: { label: string; count: number | null }[] = [
    { label: "Projects", count: projects.data?.total ?? null },
    { label: "Provider connections", count: connections.data?.total ?? null },
    { label: "Budgets", count: budgets.data?.total ?? null },
    { label: "Open alerts", count: alerts.data?.total ?? null },
    { label: "Members", count: members.data?.total ?? null },
    { label: "API keys", count: apiKeys.data?.total ?? null },
    { label: "Pending invitations", count: invitations.data?.total ?? null },
  ];
  const loading = [projects, budgets, members, apiKeys, alerts, invitations, connections].some(
    (q) => q.isLoading,
  );

  return (
    <div className="mt-3 rounded-lg border border-danger/20 bg-danger-dim px-3 py-2.5">
      <p className="mb-1.5 text-xs font-semibold text-danger">This will permanently delete:</p>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-tx-muted">
          <Loader2 size={12} className="animate-spin" />
          Calculating impact…
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-tx-secondary">
          {rows.map((r) => (
            <li key={r.label} className="flex items-center justify-between gap-2">
              <span>{r.label}</span>
              <span className="font-mono font-semibold text-tx-primary">{r.count ?? "—"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LinkedAccountsCard() {
  const { user, updateUser } = useAuthStore();

  const linkMutation = useMutation({
    mutationFn: startGoogleLink,
    onSuccess: (data) => {
      window.location.href = data.authorize_url;
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not start Google linking. Please try again.",
      );
      toast.error(title, description);
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: unlinkGoogle,
    onSuccess: (updated) => {
      updateUser({ google_linked: updated.google_linked, google_email: updated.google_email });
      toast.success("Google account unlinked");
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not unlink Google. Set a password first if this is your only sign-in method.",
      );
      toast.error(title, description);
    },
  });

  return (
    <SectionCard
      title="Linked Accounts"
      icon={Link2}
      description="Sign in faster with a connected provider."
    >
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-subtle bg-app-bg/60 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <GoogleGlyph className="h-5 w-5 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-tx-primary">Google</p>
            <p className="truncate text-xs text-tx-muted">
              {user?.google_linked ? (user.google_email ?? "Connected") : "Not connected"}
            </p>
          </div>
        </div>
        {user?.google_linked ? (
          <button
            type="button"
            onClick={() => unlinkMutation.mutate()}
            disabled={unlinkMutation.isPending}
            className="btn-outline inline-flex h-8 items-center gap-1.5 px-3 text-xs disabled:opacity-60"
          >
            {unlinkMutation.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Unlink size={12} />
            )}
            Unlink
          </button>
        ) : (
          <button
            type="button"
            onClick={() => linkMutation.mutate()}
            disabled={linkMutation.isPending}
            className="btn-outline inline-flex h-8 items-center gap-1.5 px-3 text-xs disabled:opacity-60"
          >
            {linkMutation.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Link2 size={12} />
            )}
            Link Google account
          </button>
        )}
      </div>
      <div>
        <label className="mb-1.5 block text-xs text-tx-muted">Last login provider</label>
        <input
          readOnly
          value={
            user?.last_login_provider
              ? user.last_login_provider === "google"
                ? "Google"
                : "Password"
              : "—"
          }
          className="w-full cursor-not-allowed rounded-lg border border-border-subtle bg-app-muted px-3 py-2 text-sm text-tx-muted"
        />
      </div>
    </SectionCard>
  );
}

const SCHEDULER_INTERVAL_OPTIONS: { value: SchedulerInterval; label: string }[] = [
  { value: "5m", label: "Every 5 minutes" },
  { value: "15m", label: "Every 15 minutes" },
  { value: "1h", label: "Every hour" },
  { value: "6h", label: "Every 6 hours" },
  { value: "24h", label: "Daily" },
];

const SCHEDULER_HEALTH_LABEL: Record<string, string> = {
  healthy: "Healthy",
  degraded: "Degraded — last sync failed",
  disabled: "Disabled",
  not_running: "Scheduler not running",
};

/** EP-23.4 — organization-level automatic sync configuration. Lives on the
 * Workspace tab (not Preferences, which is per-user) since auto-sync is an
 * organization setting shared by every member, exactly like the workspace
 * name/description above it. */
function AutomaticSyncCard({ organizationId }: { organizationId: string }) {
  const queryClient = useQueryClient();

  const schedulerQuery = useQuery({
    queryKey: ["scheduler-status", organizationId],
    queryFn: () => getSchedulerStatus(organizationId),
  });

  const updateMutation = useMutation({
    mutationFn: (body: { auto_sync_enabled?: boolean; interval?: SchedulerInterval }) =>
      updateSchedulerSettings(organizationId, body),
    onSuccess: (data) => {
      queryClient.setQueryData(["scheduler-status", organizationId], data);
      toast.success("Automatic sync updated");
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Please try again.");
      toast.error(title, description);
    },
  });

  const data = schedulerQuery.data;

  return (
    <SectionCard
      title="Automatic Sync"
      description="Keep provider usage data up to date without manually clicking Sync."
      icon={Timer}
    >
      {schedulerQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }, (_, i) => (
            <div key={i} className="skeleton h-9 rounded-lg" />
          ))}
        </div>
      ) : !data ? (
        <p className="text-xs text-tx-muted">Couldn't load scheduler settings.</p>
      ) : (
        <>
          <SettingRow
            label="Auto Sync"
            description="Automatically sync usage from every connected provider in the background."
          >
            <button
              role="switch"
              aria-checked={data.auto_sync_enabled}
              onClick={() => updateMutation.mutate({ auto_sync_enabled: !data.auto_sync_enabled })}
              disabled={updateMutation.isPending}
              className={cn(
                "relative h-6 w-11 rounded-full transition-colors disabled:opacity-60",
                data.auto_sync_enabled ? "bg-brand" : "bg-app-muted",
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform",
                  data.auto_sync_enabled ? "translate-x-5" : "translate-x-0.5",
                )}
              />
            </button>
          </SettingRow>

          {data.auto_sync_enabled && (
            <SettingRow
              label="Interval"
              description="How often the scheduler checks for new usage."
            >
              <select
                value={data.interval}
                onChange={(e) =>
                  updateMutation.mutate({ interval: e.target.value as SchedulerInterval })
                }
                disabled={updateMutation.isPending}
                className="rounded-lg border border-border bg-app-bg px-3 py-1.5 text-sm text-tx-primary focus:border-brand focus:outline-none disabled:opacity-60"
              >
                {SCHEDULER_INTERVAL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </SettingRow>
          )}

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border-subtle pt-1 text-xs text-tx-muted">
            <span className="inline-flex items-center gap-1.5">
              <Clock size={12} />
              Last sync: {data.last_sync_at ? formatDateTime(data.last_sync_at) : "never"}
            </span>
            {data.auto_sync_enabled && (
              <span className="inline-flex items-center gap-1.5">
                <Clock size={12} />
                Next sync: {data.next_sync_at ? formatDateTime(data.next_sync_at) : "—"}
              </span>
            )}
            <span>
              Scheduler: {SCHEDULER_HEALTH_LABEL[data.scheduler_health] ?? data.scheduler_health}
            </span>
          </div>
        </>
      )}
    </SectionCard>
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
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-tx-primary">{label}</p>
        {description && <p className="mt-0.5 text-xs text-tx-muted">{description}</p>}
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
        "h-5.5 relative w-10 flex-shrink-0 rounded-full border transition-colors duration-base",
        value ? "border-brand bg-brand" : "border-border bg-app-muted",
      )}
      aria-checked={value}
      aria-label={label}
      role="switch"
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-md transition-transform duration-base",
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
      <label htmlFor={fieldId} className="mb-1.5 block text-xs text-tx-muted">
        {label}
      </label>
      <input
        ref={ref}
        id={fieldId}
        {...rest}
        className={cn(
          "w-full rounded-lg border bg-app-bg px-3 py-2 text-sm text-tx-primary",
          "transition-colors placeholder:text-tx-muted focus:border-brand focus:outline-none",
          error ? "border-danger" : "border-border",
        )}
      />
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
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
  const resetOnboardingWidget = useOnboardingWidgetStore((s) => s.reset);
  const [active, setActive] = useState<(typeof SECTIONS)[number]["id"]>("profile");
  const [searchParams, setSearchParams] = useSearchParams();

  const preferences = user?.preferences ?? {};

  // EP-24.5: the Google OAuth callback redirects back here after a
  // successful link with `?google_linked=1` — the handoff payload itself
  // carries no updated user fields (it's a plain redirect, not a fetch
  // response), so refetch /me once to pick up google_linked/google_email,
  // then strip the query param so a page refresh doesn't re-toast.
  useEffect(() => {
    if (searchParams.get("google_linked") !== "1") return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("google_linked");
        return next;
      },
      { replace: true },
    );
    void getMe().then((me) => {
      updateUser({ google_linked: me.google_linked, google_email: me.google_email });
      toast.success("Google account linked");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

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
      const { title, description } = apiErrorMessage(
        err,
        "Could not save your profile. Please try again.",
      );
      toast.error(title, description);
    },
  });

  function onSaveProfile(data: ProfileForm) {
    const result = profileSchema.safeParse(data);
    if (!result.success) {
      toast.error(
        "Couldn't save profile",
        result.error.issues[0]?.message ?? "Fix the highlighted fields.",
      );
      return;
    }
    profileMutation.mutate(result.data);
  }

  // ── Email verification (EP-24.4) ─────────────────────────────────────────

  const resendVerificationMutation = useMutation({
    mutationFn: () => resendVerification(user?.email ?? ""),
    onSuccess: () => {
      toast.success("Verification email sent", "Check your inbox for the link.");
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not send the email. Please try again.",
      );
      toast.error(title, description);
    },
  });

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
      setOrganization(updated.id, updated.name, updated.is_personal);
      void orgsQuery.refetch();
      setWorkspaceSaved(true);
      toast.success("Workspace updated");
      setTimeout(() => setWorkspaceSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not save workspace settings. Please try again.",
      );
      toast.error(title, description);
    },
  });

  function onSaveWorkspace(data: WorkspaceForm) {
    const result = workspaceSchema.safeParse(data);
    if (!result.success) {
      toast.error(
        "Couldn't save workspace",
        result.error.issues[0]?.message ?? "Fix the highlighted fields.",
      );
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
      toast.success(
        "Password updated",
        "You're still signed in here — every other session was signed out.",
      );
      setTimeout(() => setPasswordSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not update your password. Please try again.",
      );
      toast.error(title, description);
    },
  });

  function onSavePassword(data: PasswordForm) {
    const result = passwordSchema.safeParse(data);
    if (!result.success) {
      toast.error(
        "Couldn't update password",
        result.error.issues[0]?.message ?? "Check the fields and try again.",
      );
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
      const { title, description } = apiErrorMessage(
        err,
        "Could not save this preference. Please try again.",
      );
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
  const [deleteWorkspaceConfirmText, setDeleteWorkspaceConfirmText] = useState("");
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("");

  const deleteWorkspaceMutation = useMutation({
    mutationFn: () => deleteOrganization(organizationId!),
    onSuccess: () => {
      toast.success("Workspace deleted");
      clearOrganization();
      setDeleteWorkspaceOpen(false);
      setDeleteWorkspaceConfirmText("");
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not delete this workspace. Please try again.",
      );
      toast.error(title, description);
      setDeleteWorkspaceOpen(false);
      setDeleteWorkspaceConfirmText("");
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: () => deleteAccount(deleteAccountPassword),
    onSuccess: () => {
      toast.success("Account deleted");
      clearAuth();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not delete your account. Please try again.",
      );
      toast.error(title, description);
    },
  });

  const displayName = user?.display_name ?? "";

  return (
    <div className="max-w-5xl p-4 sm:p-6">
      <PageHeader
        title="Settings"
        description="Manage your profile, workspace, and account preferences."
      />

      <div className="mt-6 flex flex-col gap-6 lg:flex-row">
        {/* Tab list */}
        <div className="flex-shrink-0 lg:w-52">
          <div className="flex gap-1 overflow-x-auto rounded-lg border border-border-subtle bg-app-card p-1 lg:flex-col lg:overflow-visible lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0">
            {/* EP-25.1 — the Workspace tab is org rename/description/delete,
                none of which apply to a personal (single-user, never
                renameable/deletable) workspace — hidden entirely rather than
                shown-but-disabled. */}
            {SECTIONS.filter((s) => s.id !== "workspace" || !currentOrg?.is_personal).map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cn(
                  "flex flex-shrink-0 items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-all",
                  active === s.id
                    ? s.id === "danger"
                      ? "bg-danger-dim text-danger"
                      : "bg-brand-subtle text-brand"
                    : "text-tx-secondary hover:bg-app-hover hover:text-tx-primary",
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
            <>
              <form
                onSubmit={(e) => {
                  void handleProfileSubmit(onSaveProfile)(e);
                }}
              >
                <SectionCard title="Profile" icon={User}>
                  <div className="flex items-center gap-4">
                    <Avatar name={displayName || "Account"} size={64} />
                    <div>
                      <p className="text-sm font-medium text-tx-primary">{displayName}</p>
                      <p className="text-xs text-tx-muted">{user?.email}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-xs text-tx-muted">Email address</label>
                      <input
                        readOnly
                        value={user?.email ?? ""}
                        className="w-full cursor-not-allowed rounded-lg border border-border-subtle bg-app-muted px-3 py-2 text-sm text-tx-muted"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs text-tx-muted">Account status</label>
                      <input
                        readOnly
                        value={user?.status ?? ""}
                        className="w-full cursor-not-allowed rounded-lg border border-border-subtle bg-app-muted px-3 py-2 text-sm capitalize text-tx-muted"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs text-tx-muted">Email verification</label>
                    {user?.email_verified ? (
                      <div className="flex items-center gap-2 rounded-lg border border-success/20 bg-success-dim px-3 py-2">
                        <MailCheck size={14} className="flex-shrink-0 text-success" />
                        <span className="text-sm text-success">Verified</span>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/20 bg-warning-dim px-3 py-2">
                        <Mail size={14} className="flex-shrink-0 text-warning" />
                        <span className="min-w-[10rem] flex-1 text-sm text-warning">
                          Not verified
                        </span>
                        <button
                          type="button"
                          onClick={() => resendVerificationMutation.mutate()}
                          disabled={resendVerificationMutation.isPending}
                          className="btn-outline inline-flex h-8 items-center gap-1.5 px-3 text-xs disabled:opacity-60"
                        >
                          {resendVerificationMutation.isPending ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : null}
                          {resendVerificationMutation.isPending
                            ? "Sending…"
                            : "Resend verification email"}
                        </button>
                      </div>
                    )}
                  </div>

                  {user?.created_at && (
                    <div>
                      <label className="mb-1.5 block text-xs text-tx-muted">Member since</label>
                      <input
                        readOnly
                        value={formatDateTime(user.created_at)}
                        className="w-full cursor-not-allowed rounded-lg border border-border-subtle bg-app-muted px-3 py-2 text-sm text-tx-muted"
                      />
                    </div>
                  )}

                  <div>
                    <label htmlFor="bio" className="mb-1.5 block text-xs text-tx-muted">
                      Bio (optional)
                    </label>
                    <textarea
                      id="bio"
                      rows={3}
                      {...registerProfile("bio")}
                      placeholder="Tell us a little about yourself"
                      className={cn(
                        "w-full resize-none rounded-lg border bg-app-bg px-3 py-2 text-sm text-tx-primary",
                        "transition-colors placeholder:text-tx-muted focus:border-brand focus:outline-none",
                        profileErrors.bio ? "border-danger" : "border-border",
                      )}
                    />
                    {profileErrors.bio && (
                      <p className="mt-1 text-xs text-danger">{profileErrors.bio.message}</p>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={profileMutation.isPending}
                    className={cn(
                      "btn-primary w-fit",
                      profileSaved && "bg-success hover:bg-success",
                    )}
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
              <LinkedAccountsCard />
              {currentOrg?.is_personal && (
                <UpgradeToBusinessCard onUpgraded={() => void orgsQuery.refetch()} />
              )}
            </>
          )}

          {active === "workspace" && (
            <form
              onSubmit={(e) => {
                void handleWorkspaceSubmit(onSaveWorkspace)(e);
              }}
            >
              <SectionCard title="Workspace" icon={Building2}>
                {orgsQuery.isLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }, (_, i) => (
                      <div key={i} className="skeleton h-9 rounded-lg" />
                    ))}
                  </div>
                ) : !currentOrg ? (
                  <p className="text-xs text-tx-muted">
                    Select a workspace to manage its settings.
                  </p>
                ) : (
                  <>
                    <TextField label="Workspace name" {...registerWorkspace("name")} />
                    <div>
                      <label
                        htmlFor="ws-description"
                        className="mb-1.5 block text-xs text-tx-muted"
                      >
                        Description (optional)
                      </label>
                      <textarea
                        id="ws-description"
                        rows={3}
                        {...registerWorkspace("description")}
                        placeholder="What is this workspace for?"
                        className="w-full resize-none rounded-lg border border-border bg-app-bg px-3 py-2 text-sm text-tx-primary transition-colors placeholder:text-tx-muted focus:border-brand focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <div>
                        <label className="mb-1.5 block text-xs text-tx-muted">Slug</label>
                        <input
                          readOnly
                          value={currentOrg.slug}
                          className="w-full cursor-not-allowed rounded-lg border border-border-subtle bg-app-muted px-3 py-2 font-mono text-sm text-tx-muted"
                        />
                      </div>
                      <div>
                        <label className="mb-1.5 block text-xs text-tx-muted">
                          Organization ID
                        </label>
                        <input
                          readOnly
                          value={currentOrg.id}
                          className="w-full cursor-not-allowed truncate rounded-lg border border-border-subtle bg-app-muted px-3 py-2 font-mono text-sm text-tx-muted"
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {currentOrg.is_personal && (
                        <span className="badge bg-brand-subtle text-[10px] uppercase tracking-wide text-brand">
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
                      className={cn(
                        "btn-primary w-fit",
                        workspaceSaved && "bg-success hover:bg-success",
                      )}
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

          {active === "workspace" && currentOrg && (
            <AutomaticSyncCard organizationId={currentOrg.id} />
          )}

          {active === "password" && (
            <form
              onSubmit={(e) => {
                void handlePasswordSubmit(onSavePassword)(e);
              }}
            >
              <SectionCard
                title="Password"
                icon={Shield}
                description="Changing your password signs out every other session."
              >
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                  className={cn(
                    "btn-primary w-fit",
                    passwordSaved && "bg-success hover:bg-success",
                  )}
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
                <SettingRow
                  label="Theme"
                  description="Neon Cyber, Professional Light, or Professional Dark"
                >
                  <div className="flex gap-1 rounded-lg border border-border-subtle bg-app-bg p-0.5">
                    {THEMES.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => onChangeTheme(t.id)}
                        aria-pressed={theme === t.id}
                        className={cn(
                          "whitespace-nowrap rounded-md px-3 py-1 text-xs font-medium transition-all",
                          theme === t.id
                            ? "bg-brand text-app-bg"
                            : "text-tx-muted hover:text-tx-secondary",
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
                    className="rounded-lg border border-border bg-app-bg px-3 py-2 text-sm text-tx-primary focus:border-brand focus:outline-none"
                  >
                    {["USD", "EUR", "GBP"].map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </SettingRow>
                <SettingRow label="Collapse sidebar" description="Start with the sidebar collapsed">
                  <Toggle
                    value={sidebarCollapsed}
                    onChange={onToggleSidebar}
                    label="Collapse sidebar"
                  />
                </SettingRow>
              </SectionCard>

              <SectionCard title="Regional" icon={Palette}>
                <SettingRow label="Timezone" description="Used to display dates and times">
                  <select
                    value={pref(preferences, "timezone", "UTC")}
                    onChange={(e) => onChangeTimezone(e.target.value)}
                    className="rounded-lg border border-border bg-app-bg px-3 py-2 text-sm text-tx-primary focus:border-brand focus:outline-none"
                  >
                    {(TIMEZONES.includes(pref(preferences, "timezone", "UTC"))
                      ? TIMEZONES
                      : [pref(preferences, "timezone", "UTC"), ...TIMEZONES]
                    ).map((tz) => (
                      <option key={tz} value={tz}>
                        {tz}
                      </option>
                    ))}
                  </select>
                </SettingRow>
                <SettingRow
                  label="Date format"
                  description="How dates are displayed across the dashboard"
                >
                  <select
                    value={pref(preferences, "date_format", "MM/DD/YYYY")}
                    onChange={(e) => onChangeDateFormat(e.target.value)}
                    className="rounded-lg border border-border bg-app-bg px-3 py-2 text-sm text-tx-primary focus:border-brand focus:outline-none"
                  >
                    {DATE_FORMATS.map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </SettingRow>
              </SectionCard>

              <SectionCard title="Notification Preferences" icon={Bell}>
                {[
                  {
                    key: "budget",
                    label: "Budget alerts",
                    desc: "Alert when projects exceed 80% budget",
                  },
                  {
                    key: "anomaly",
                    label: "Anomaly detection",
                    desc: "Notify on unusual cost spikes",
                  },
                  { key: "weekly", label: "Weekly digest", desc: "Weekly cost summary email" },
                  {
                    key: "security",
                    label: "Security events",
                    desc: "Sign-ins and permission changes",
                  },
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

              {/* EP-25.4.4 Part 1 — reverses "Never show again" on the
                  dashboard's Getting Started widget (features/Overview.tsx's
                  OnboardingWidget). This is a per-browser preference
                  (stores/onboardingWidget.ts), not a backend field — there
                  is nothing server-side to reset. */}
              <SectionCard
                title="Dashboard"
                icon={Rocket}
                description="Controls for the Overview page's Getting Started widget."
              >
                <SettingRow
                  label="Getting Started widget"
                  description="Bring back the setup checklist if you previously dismissed it with “Never show again.”"
                >
                  <button
                    onClick={() => {
                      resetOnboardingWidget();
                      toast.success("Onboarding reset", "The Getting Started widget will show again on Overview.");
                    }}
                    className="flex h-8 items-center gap-1.5 rounded-lg border border-border-subtle bg-app-bg px-3 text-xs font-medium text-tx-secondary hover:text-tx-primary"
                  >
                    <RotateCcw size={12} />
                    Reset onboarding
                  </button>
                </SettingRow>
              </SectionCard>
            </>
          )}

          {active === "api-keys" && (
            <SectionCard
              title="API Keys"
              icon={KeyRound}
              description="Programmatic access to your organization's data."
            >
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
                    className="flex h-9 w-fit items-center gap-1.5 rounded-lg bg-danger px-3.5 text-xs font-semibold text-white hover:bg-danger-light disabled:opacity-50"
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
                  className="flex h-9 w-fit items-center gap-1.5 rounded-lg bg-danger px-3.5 text-xs font-semibold text-white hover:bg-danger-light"
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
        description="This permanently deletes the workspace and everything in it. This cannot be undone."
        confirmLabel="Delete workspace"
        loading={deleteWorkspaceMutation.isPending}
        confirmDisabled={!typeToConfirmMatches(organizationName ?? "", deleteWorkspaceConfirmText)}
        onConfirm={() => deleteWorkspaceMutation.mutate()}
        onCancel={() => {
          setDeleteWorkspaceOpen(false);
          setDeleteWorkspaceConfirmText("");
        }}
      >
        {deleteWorkspaceOpen && organizationId && (
          <WorkspaceImpactSummary organizationId={organizationId} />
        )}
        <TypeToConfirmField
          id="confirm-delete-workspace"
          expected={organizationName ?? ""}
          value={deleteWorkspaceConfirmText}
          onChange={setDeleteWorkspaceConfirmText}
          disabled={deleteWorkspaceMutation.isPending}
        />
      </ConfirmDialog>

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
          className="mt-3 w-full rounded-lg border border-border bg-app-bg px-3 py-2 text-sm text-tx-primary placeholder:text-tx-muted focus:border-danger focus:outline-none"
        />
      </ConfirmDialog>
    </div>
  );
}
