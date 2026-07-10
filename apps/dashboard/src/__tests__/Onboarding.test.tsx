import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Onboarding from "../features/Onboarding";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";

// EP-21.3 — the 5-step first-time onboarding wizard, now reusing the real
// EP-22 provider-connection form (Step 3) instead of a static placeholder.

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    completeOnboarding: vi.fn(),
    getOrganizations: vi.fn(),
    updateOrganization: vi.fn(),
    listProviderConnections: vi.fn(),
    createProviderConnection: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const baseUser = {
  id: "usr_1",
  email: "ada@example.com",
  username: null,
  display_name: "Ada Lovelace",
  status: "active",
  email_verified: true,
  avatar_url: null,
  bio: null,
  timezone: null,
  created_at: "2026-01-01T00:00:00Z",
  preferences: {},
  google_linked: false,
  google_email: null,
  last_login_provider: null,
  password_configured: true,
};

function renderOnboarding() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/onboarding"]}>
        <Routes>
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/dashboard" element={<div>dashboard-page</div>} />
          <Route path="/connections" element={<div>connections-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Onboarding — first-time wizard (EP-21.3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Ada's Workspace" });
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        {
          id: "org_1",
          name: "Ada's Workspace",
          slug: "ada-workspace",
          role: "owner",
          is_personal: false,
        },
      ],
    });
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
  });

  it("shows the welcome step with the user's first name for an incomplete session", () => {
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });
    renderOnboarding();
    expect(screen.getByText(/Welcome to Costorah, Ada/i)).toBeTruthy();
  });

  it("redirects straight to the dashboard when onboarding is already complete", async () => {
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: true });
    renderOnboarding();
    await waitFor(() => expect(screen.getByText("dashboard-page")).toBeTruthy());
    expect(screen.queryByText(/Welcome to Costorah/i)).toBeNull();
  });

  it("walks through Welcome -> Workspace -> Provider -> Tour -> Finish", async () => {
    const user = userEvent.setup();
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });
    renderOnboarding();

    // Step 1: Welcome
    await user.click(screen.getByRole("button", { name: /get started/i }));

    // Step 2: Workspace
    expect(await screen.findByText("Ada's Workspace")).toBeTruthy();
    expect(screen.getByText("ada-workspace")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Step 3: Provider — reuses the real Connect Provider form
    expect(await screen.findByText(/Connect your first provider/i)).toBeTruthy();
    expect(screen.getByText("OpenAI")).toBeTruthy();
    expect(screen.getByText("Ollama")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /skip for now/i }));

    // Step 4: Tour
    expect(await screen.findByText(/A quick tour/i)).toBeTruthy();
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(screen.getByText("Projects")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Step 5: Finish
    expect(await screen.findByText(/You're ready/i)).toBeTruthy();
  });

  it("EP-25.2: shows 'My Account' instead of a renameable Workspace step for a personal org", async () => {
    const user = userEvent.setup();
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        {
          id: "org_1",
          name: "Ada's Workspace",
          slug: "ada-workspace",
          role: "owner",
          is_personal: true,
        },
      ],
    });
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });
    renderOnboarding();

    await user.click(screen.getByRole("button", { name: /get started/i }));

    expect(await screen.findByText("My Account")).toBeTruthy();
    expect(screen.queryByText("Ada's Workspace")).toBeNull();
    expect(screen.queryByLabelText(/Edit workspace name/i)).toBeNull();
    expect(screen.queryByText(/Workspace name/i)).toBeNull();
  });

  it("lets the user connect a real provider inline during Step 3", async () => {
    const user = userEvent.setup();
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });
    mockedApi.createProviderConnection.mockResolvedValue({
      id: "conn_1",
      provider_type: "openai",
      display_name: "My OpenAI",
      project_id: null,
      is_active: true,
      has_credential: true,
      masked_api_key: "sk-***AbC",
      base_url: null,
      health_status: "healthy",
      last_validation_status: "healthy",
      last_error: null,
      last_failure_at: null,
      last_recovery_at: null,
      consecutive_failure_count: 0,
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    });

    renderOnboarding();
    await user.click(screen.getByRole("button", { name: /get started/i }));
    await screen.findByText("Ada's Workspace");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    await screen.findByText(/Connect your first provider/i);
    await user.click(screen.getByRole("button", { name: /^connect provider$/i }));

    const nameInput = await screen.findByPlaceholderText(/Connection name/i);
    await user.type(nameInput, "My OpenAI");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(mockedApi.createProviderConnection).toHaveBeenCalled());
    // Successful connect auto-advances to the Tour step.
    expect(await screen.findByText(/A quick tour/i)).toBeTruthy();
  });

  it("persists onboarding completion and redirects when Finish -> Go to dashboard is clicked", async () => {
    const user = userEvent.setup();
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });
    mockedApi.completeOnboarding.mockResolvedValue({ ...baseUser, onboarding_completed: true });

    renderOnboarding();
    await user.click(screen.getByRole("button", { name: /get started/i }));
    await screen.findByText("Ada's Workspace");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByText(/Connect your first provider/i);
    await user.click(screen.getByRole("button", { name: /skip for now/i }));
    await screen.findByText(/A quick tour/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));

    await user.click(await screen.findByRole("button", { name: /go to dashboard/i }));

    await waitFor(() => expect(mockedApi.completeOnboarding).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("dashboard-page")).toBeTruthy());
  });
});
