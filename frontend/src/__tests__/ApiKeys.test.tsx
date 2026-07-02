import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ApiKeys from "../features/ApiKeys";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { ApiKey, ApiKeyCreatedResponse, PermissionsResponse } from "../services/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listApiKeys: vi.fn(),
    createApiKey: vi.fn(),
    revokeApiKey: vi.fn(),
    listPermissions: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const SAMPLE_KEY: ApiKey = {
  id: "key_1",
  name: "Prod ingestion",
  description: "Used by the nightly job",
  prefix: "costorah_live_ab12cd34",
  permissions: ["usage:read"],
  created_at: "2026-06-01T00:00:00Z",
  expires_at: null,
  last_used_at: null,
};

const SAMPLE_PERMISSIONS: PermissionsResponse = {
  permissions: [
    { permission: "usage:read", domain: "usage", action: "read" },
    { permission: "org:read", domain: "org", action: "read" },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiKeys />
    </QueryClientProvider>,
  );
}

describe("ApiKeys page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.listPermissions.mockResolvedValue(SAMPLE_PERMISSIONS);
  });

  it("shows the empty state when there are no keys", async () => {
    mockedApi.listApiKeys.mockResolvedValue({ keys: [], total: 0 });
    renderPage();
    expect(await screen.findByText(/No API Keys created yet/i)).toBeTruthy();
    expect(screen.getByText(/Create your first API Key/i)).toBeTruthy();
  });

  it("renders a list of keys with their metadata", async () => {
    mockedApi.listApiKeys.mockResolvedValue({ keys: [SAMPLE_KEY], total: 1 });
    renderPage();
    expect(await screen.findByText("Prod ingestion")).toBeTruthy();
    expect(screen.getByText("costorah_live_ab12cd34")).toBeTruthy();
    expect(screen.getByText("Never")).toBeTruthy();
    expect(screen.getByText("Never used")).toBeTruthy();
  });

  it("shows an error state when the list request fails", async () => {
    mockedApi.listApiKeys.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByText(/Couldn't load API keys/i)).toBeTruthy();
  });

  it("creates a key and reveals the raw secret exactly once", async () => {
    const user = userEvent.setup();
    mockedApi.listApiKeys.mockResolvedValue({ keys: [], total: 0 });
    const created: ApiKeyCreatedResponse = {
      id: "key_2",
      api_key: "costorah_live_supersecretvalue1234567890",
      prefix: "costorah_live_supers",
      name: "New key",
      permissions: [],
      created_at: "2026-07-01T00:00:00Z",
      expires_at: null,
    };
    mockedApi.createApiKey.mockResolvedValue(created);

    renderPage();
    await screen.findByText(/No API Keys created yet/i);

    await user.click(screen.getAllByRole("button", { name: /create api key/i })[0]!);

    const dialog = await screen.findByRole("dialog", { name: "Create API Key" });
    const nameInput = within(dialog).getByLabelText("Name");
    await user.type(nameInput, "New key");
    await waitFor(() => expect(nameInput).toHaveValue("New key"));
    await user.click(within(dialog).getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(mockedApi.createApiKey).toHaveBeenCalledWith("org_1", {
        name: "New key",
        permissions: [],
        expiration: "never",
      });
    });

    expect(await screen.findByText("API Key Created")).toBeTruthy();
    expect(screen.getByText(/Copy this key now/i)).toBeTruthy();
    expect(screen.getByDisplayValue(created.api_key)).toBeTruthy();
  });

  it("revokes a key after confirming the destructive dialog", async () => {
    const user = userEvent.setup();
    mockedApi.listApiKeys.mockResolvedValue({ keys: [SAMPLE_KEY], total: 1 });
    mockedApi.revokeApiKey.mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Prod ingestion");

    await user.click(screen.getByRole("button", { name: /delete prod ingestion/i }));

    const confirm = await screen.findByRole("alertdialog", { name: /delete api key/i });
    expect(within(confirm).getByText(/cannot be undone/i)).toBeTruthy();

    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(mockedApi.revokeApiKey).toHaveBeenCalledWith("org_1", "key_1");
    });
  });

  it("does not call revoke when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    mockedApi.listApiKeys.mockResolvedValue({ keys: [SAMPLE_KEY], total: 1 });

    renderPage();
    await screen.findByText("Prod ingestion");
    await user.click(screen.getByRole("button", { name: /delete prod ingestion/i }));

    const confirm = await screen.findByRole("alertdialog", { name: /delete api key/i });
    await user.click(within(confirm).getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });
    expect(mockedApi.revokeApiKey).not.toHaveBeenCalled();
  });
});
