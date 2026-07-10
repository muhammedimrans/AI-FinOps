import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";

// features/Settings.tsx imports the theme store (via features/ApiKeys ->
// ... no direct chain, but Settings itself imports stores/theme directly),
// which reads window.matchMedia on first access — jsdom doesn't implement
// it, so stub it before that import runs (same pattern as
// GettingStartedBanner.test.tsx).
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
}

const { default: Settings } = await import("../features/Settings");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    updateProfile: vi.fn(),
    updatePreferences: vi.fn(),
    changePassword: vi.fn(),
    deleteAccount: vi.fn(),
    getOrganizations: vi.fn(),
    updateOrganization: vi.fn(),
    deleteOrganization: vi.fn(),
    listApiKeys: vi.fn(),
    listPermissions: vi.fn(),
    getSchedulerStatus: vi.fn(),
    updateSchedulerSettings: vi.fn(),
    resendVerification: vi.fn(),
    startGoogleLink: vi.fn(),
    unlinkGoogle: vi.fn(),
    getMe: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const baseUser = {
  id: "usr_1",
  email: "ada@example.com",
  username: "ada",
  display_name: "Ada Lovelace",
  status: "active",
  email_verified: true,
  onboarding_completed: true,
  avatar_url: null,
  bio: null,
  timezone: null,
  created_at: "2026-01-01T00:00:00Z",
  preferences: { theme: "professional-dark" } as Record<string, unknown>,
  google_linked: false,
  google_email: null,
  last_login_provider: null,
  password_configured: true,
};

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/settings"]}>
      <QueryClientProvider client={queryClient}>
        <Settings />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Settings — EP-22.2 backend integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setLogin("access.token", "refresh.token", baseUser);
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        {
          id: "org_1",
          name: "Acme",
          slug: "acme",
          role: "owner",
          description: "We build things.",
          is_personal: false,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.listApiKeys.mockResolvedValue({ keys: [], total: 0 });
    mockedApi.listPermissions.mockResolvedValue({ permissions: [] });
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: false,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: null,
      current_job: null,
      scheduler_health: "disabled",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });
  });

  it("renders the Profile section by default with the current user's info", () => {
    renderSettings();
    expect(screen.getByDisplayValue("Ada Lovelace")).toBeTruthy();
    expect(screen.getByDisplayValue("ada")).toBeTruthy();
    expect(screen.getByDisplayValue("ada@example.com")).toBeTruthy();
  });

  it("shows a Verified badge and no resend button when the email is verified", () => {
    renderSettings();
    expect(screen.getByText("Verified")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /resend verification/i })).toBeNull();
  });

  it("shows Not verified with a resend button, and calls resendVerification on click", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      email_verified: false,
    });
    mockedApi.resendVerification.mockResolvedValue({
      message: "If an account with that email exists and isn't verified, a new link has been sent",
    });
    renderSettings();

    expect(screen.getByText("Not verified")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /resend verification/i }));

    await waitFor(() => {
      expect(mockedApi.resendVerification).toHaveBeenCalledWith("ada@example.com");
    });
  });

  it("saves profile changes via PATCH /v1/auth/me", async () => {
    const user = userEvent.setup();
    mockedApi.updateProfile.mockResolvedValue({ ...baseUser, display_name: "Ada L." });
    renderSettings();

    const nameInput = screen.getByDisplayValue("Ada Lovelace");
    await user.clear(nameInput);
    await user.type(nameInput, "Ada L.");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(mockedApi.updateProfile).toHaveBeenCalledWith(
        expect.objectContaining({ display_name: "Ada L." }),
      );
    });
  });

  it("loads and saves workspace name/description via PATCH /v1/organizations/{id}", async () => {
    const user = userEvent.setup();
    mockedApi.updateOrganization.mockResolvedValue({
      id: "org_1",
      name: "Acme Inc",
      slug: "acme",
      role: "owner",
      description: "We build things.",
      is_personal: false,
      created_at: "2026-01-01T00:00:00Z",
    });
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Workspace" }));
    const nameInput = await screen.findByDisplayValue("Acme");
    await user.clear(nameInput);
    await user.type(nameInput, "Acme Inc");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(mockedApi.updateOrganization).toHaveBeenCalledWith("org_1", {
        name: "Acme Inc",
        description: "We build things.",
      });
    });
  });

  it("changes password and shows a success message", async () => {
    const user = userEvent.setup();
    mockedApi.changePassword.mockResolvedValue({ message: "Password changed successfully" });
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Password" }));
    await user.type(await screen.findByLabelText("Current password"), "old-password-1");
    await user.type(screen.getByLabelText("New password"), "new-password-2");
    await user.type(screen.getByLabelText("Confirm new password"), "new-password-2");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(mockedApi.changePassword).toHaveBeenCalledWith("old-password-1", "new-password-2");
    });
    expect(await screen.findByText(/Updated!/i)).toBeTruthy();
  });

  it("rejects a password change when confirmation doesn't match", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Password" }));
    await user.type(await screen.findByLabelText("Current password"), "old-password-1");
    await user.type(screen.getByLabelText("New password"), "new-password-2");
    await user.type(screen.getByLabelText("Confirm new password"), "does-not-match");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(mockedApi.changePassword).not.toHaveBeenCalled();
  });

  it("toggles a preference and persists it via PATCH /v1/auth/me/preferences", async () => {
    const user = userEvent.setup();
    mockedApi.updatePreferences.mockResolvedValue({
      ...baseUser,
      preferences: { theme: "professional-dark", notifications: { weekly: true } },
    });
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Preferences" }));
    await user.click(await screen.findByRole("switch", { name: /weekly digest/i }));

    await waitFor(() => {
      expect(mockedApi.updatePreferences).toHaveBeenCalledWith({
        notifications: { budget: true, anomaly: true, weekly: true, security: true },
      });
    });
  });

  it("renders the API Keys section reusing the shared ApiKeysManager", async () => {
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByRole("button", { name: "API Keys" }));
    expect(await screen.findByText(/No API Keys created yet/i)).toBeTruthy();
  });

  it("blocks deleting the personal workspace", async () => {
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        {
          id: "org_1",
          name: "Ada's Workspace",
          slug: "ada",
          role: "owner",
          description: null,
          is_personal: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByRole("button", { name: "Danger Zone" }));
    expect(await screen.findByText(/personal workspace can't be deleted/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /delete workspace/i })).toBeNull();
  });

  it("deletes the workspace after confirmation", async () => {
    const user = userEvent.setup();
    mockedApi.deleteOrganization.mockResolvedValue(undefined);
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Danger Zone" }));
    await user.click(await screen.findByRole("button", { name: /delete workspace/i }));

    const confirm = await screen.findByRole("alertdialog", { name: /delete "acme"/i });
    await user.click(within(confirm).getByRole("button", { name: /delete workspace/i }));

    await waitFor(() => {
      expect(mockedApi.deleteOrganization).toHaveBeenCalledWith("org_1");
    });
  });

  it("requires a password before confirming account deletion", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Danger Zone" }));
    await user.click(await screen.findByRole("button", { name: /delete account/i }));

    const confirm = await screen.findByRole("alertdialog", { name: /delete your account/i });
    await user.click(within(confirm).getByRole("button", { name: /delete account/i }));

    expect(mockedApi.deleteAccount).not.toHaveBeenCalled();
  });

  it("deletes the account once a password is supplied", async () => {
    const user = userEvent.setup();
    mockedApi.deleteAccount.mockResolvedValue(undefined);
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Danger Zone" }));
    await user.click(await screen.findByRole("button", { name: /delete account/i }));

    const confirm = await screen.findByRole("alertdialog", { name: /delete your account/i });
    await user.type(within(confirm).getByPlaceholderText("Your password"), "correct-horse");
    await user.click(within(confirm).getByRole("button", { name: /delete account/i }));

    await waitFor(() => {
      expect(mockedApi.deleteAccount).toHaveBeenCalledWith("correct-horse");
    });
  });
});

describe("Settings — Automatic Sync (EP-23.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setLogin("access.token", "refresh.token", baseUser);
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        {
          id: "org_1",
          name: "Acme",
          slug: "acme",
          role: "owner",
          description: "We build things.",
          is_personal: false,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.listApiKeys.mockResolvedValue({ keys: [], total: 0 });
    mockedApi.listPermissions.mockResolvedValue({ permissions: [] });
  });

  it("shows Auto Sync as off and hides the interval picker when disabled", async () => {
    const user = userEvent.setup();
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: false,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: null,
      current_job: null,
      scheduler_health: "disabled",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });

    renderSettings();
    await user.click(screen.getByRole("button", { name: "Workspace" }));

    const toggle = await screen.findByRole("switch");
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getByText(/last sync: never/i)).toBeTruthy();
  });

  it("shows the interval picker and next-sync time when enabled", async () => {
    const user = userEvent.setup();
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: true,
      interval: "15m",
      interval_seconds: 900,
      last_sync_at: "2026-07-01T00:00:00Z",
      last_sync_status: "completed",
      next_sync_at: "2026-07-01T00:15:00Z",
      current_job: null,
      scheduler_health: "healthy",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 3,
        failed_jobs: 0,
        average_duration_seconds: 4.2,
        last_execution: "2026-07-01T00:00:00Z",
      },
    });

    renderSettings();
    await user.click(screen.getByRole("button", { name: "Workspace" }));

    const select = await screen.findByRole("combobox");
    expect((select as HTMLSelectElement).value).toBe("15m");
    expect(screen.getByText(/next sync:/i)).toBeTruthy();
    expect(screen.getByText(/scheduler: healthy/i)).toBeTruthy();
  });

  it("toggles Auto Sync on via the switch", async () => {
    const user = userEvent.setup();
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: false,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: null,
      current_job: null,
      scheduler_health: "disabled",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });
    mockedApi.updateSchedulerSettings.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: true,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: "2026-07-01T01:00:00Z",
      current_job: null,
      scheduler_health: "healthy",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });

    renderSettings();
    await user.click(screen.getByRole("button", { name: "Workspace" }));

    const toggle = await screen.findByRole("switch");
    await user.click(toggle);

    await waitFor(() => {
      expect(mockedApi.updateSchedulerSettings).toHaveBeenCalledWith("org_1", {
        auto_sync_enabled: true,
      });
    });
    expect(await screen.findByRole("combobox")).toBeTruthy();
  });

  it("changes the sync interval via the select", async () => {
    const user = userEvent.setup();
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: true,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: "2026-07-01T01:00:00Z",
      current_job: null,
      scheduler_health: "healthy",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });
    mockedApi.updateSchedulerSettings.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: true,
      interval: "6h",
      interval_seconds: 21600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: "2026-07-01T06:00:00Z",
      current_job: null,
      scheduler_health: "healthy",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });

    renderSettings();
    await user.click(screen.getByRole("button", { name: "Workspace" }));

    const select = await screen.findByRole("combobox");
    await user.selectOptions(select, "6h");

    await waitFor(() => {
      expect(mockedApi.updateSchedulerSettings).toHaveBeenCalledWith("org_1", {
        interval: "6h",
      });
    });
  });
});

describe("Settings — Linked Accounts (EP-24.5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        {
          id: "org_1",
          name: "Acme",
          slug: "acme",
          role: "owner",
          description: "We build things.",
          is_personal: false,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.listApiKeys.mockResolvedValue({ keys: [], total: 0 });
    mockedApi.listPermissions.mockResolvedValue({ permissions: [] });
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: false,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: null,
      current_job: null,
      scheduler_health: "disabled",
      monitoring: {
        is_running: true,
        active_jobs: 0,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });
  });

  it("shows 'Not connected' and a Link Google account button when not linked", () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", baseUser);
    renderSettings();

    expect(screen.getByText("Not connected")).toBeTruthy();
    expect(screen.getByRole("button", { name: /link google account/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^unlink$/i })).toBeNull();
  });

  it("shows the connected email and an Unlink button when linked", () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      google_linked: true,
      google_email: "ada@gmail.com",
      last_login_provider: "google",
    });
    renderSettings();

    expect(screen.getByText("ada@gmail.com")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^unlink$/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /link google account/i })).toBeNull();
    expect(screen.getByDisplayValue("Google")).toBeTruthy();
  });

  it("shows 'Password' as the last login provider when logged in with a password", () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      last_login_provider: "password",
    });
    renderSettings();

    expect(screen.getByDisplayValue("Password")).toBeTruthy();
  });

  it("navigates to the returned authorize_url when Link Google account is clicked", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setLogin("access.token", "refresh.token", baseUser);
    mockedApi.startGoogleLink.mockResolvedValue({
      authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
    });
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      writable: true,
      configurable: true,
      value: { href: "" },
    });

    renderSettings();
    await user.click(screen.getByRole("button", { name: /link google account/i }));

    await waitFor(() => {
      expect(mockedApi.startGoogleLink).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(window.location.href).toBe("https://accounts.google.com/o/oauth2/v2/auth?state=abc");
    });

    Object.defineProperty(window, "location", {
      writable: true,
      configurable: true,
      value: originalLocation,
    });
  });

  it("unlinks Google and updates the UI on success", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      google_linked: true,
      google_email: "ada@gmail.com",
    });
    mockedApi.unlinkGoogle.mockResolvedValue({
      ...baseUser,
      google_linked: false,
      google_email: null,
    });

    renderSettings();
    await user.click(screen.getByRole("button", { name: /^unlink$/i }));

    await waitFor(() => {
      expect(mockedApi.unlinkGoogle).toHaveBeenCalled();
    });
    expect(await screen.findByText("Not connected")).toBeTruthy();
  });

  it("refetches /me and shows the linked state after redirecting back with ?google_linked=1", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", baseUser);
    mockedApi.getMe.mockResolvedValue({
      ...baseUser,
      google_linked: true,
      google_email: "ada@gmail.com",
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <MemoryRouter initialEntries={["/settings?google_linked=1"]}>
        <QueryClientProvider client={queryClient}>
          <Settings />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockedApi.getMe).toHaveBeenCalled();
    });
    expect(await screen.findByText("ada@gmail.com")).toBeTruthy();
  });
});
