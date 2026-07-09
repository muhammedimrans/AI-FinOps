import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
};

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Settings />
    </QueryClientProvider>,
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
  });

  it("renders the Profile section by default with the current user's info", () => {
    renderSettings();
    expect(screen.getByDisplayValue("Ada Lovelace")).toBeTruthy();
    expect(screen.getByDisplayValue("ada")).toBeTruthy();
    expect(screen.getByDisplayValue("ada@example.com")).toBeTruthy();
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
    expect(
      await screen.findByText(/personal workspace can't be deleted/i),
    ).toBeTruthy();
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
