import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Connections from "../features/Connections";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type {
  ProviderConnectionRecord,
  ProviderConnectionsListResponse,
  ProviderInfoResponse,
} from "../services/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    getProviderInfo: vi.fn(),
    listProviderConnections: vi.fn(),
    createProviderConnection: vi.fn(),
    updateProviderConnection: vi.fn(),
    deleteProviderConnection: vi.fn(),
    testProviderConnectionById: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const SAMPLE_INFO: ProviderInfoResponse = {
  provider: "openai",
  display_name: "OpenAI",
  version: "1.0",
  api_version: null,
  authentication_type: "api_key",
  documentation_url: null,
  health: "healthy",
  supports_streaming: true,
  supports_tool_calling: true,
  supports_vision: true,
  supports_usage_api: true,
  supports_fine_tuning: false,
  max_context_window: 128000,
  supported_model_ids: [],
};

const SAMPLE_CONNECTION: ProviderConnectionRecord = {
  id: "conn_1",
  provider_type: "openai",
  display_name: "Production OpenAI",
  project_id: null,
  is_active: true,
  health_status: "unknown",
  last_failure_at: null,
  last_recovery_at: null,
  consecutive_failure_count: 0,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Connections />
    </QueryClientProvider>,
  );
}

describe("Connections page — Manage provider connections (EP-22)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getProviderInfo.mockResolvedValue(SAMPLE_INFO);
  });

  it("shows the empty state when there are no connections", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    renderPage();
    expect(await screen.findByText(/No provider connections yet/i)).toBeTruthy();
  });

  it("lists connections with health and active badges", async () => {
    const list: ProviderConnectionsListResponse = { connections: [SAMPLE_CONNECTION], total: 1 };
    mockedApi.listProviderConnections.mockResolvedValue(list);
    renderPage();
    expect(await screen.findByText("Production OpenAI")).toBeTruthy();
    expect(screen.getByText("Not tested")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });

  it("creates a connection via the inline form", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.createProviderConnection.mockResolvedValue(SAMPLE_CONNECTION);

    renderPage();
    await screen.findByText(/No provider connections yet/i);

    await user.click(screen.getAllByRole("button", { name: /add provider/i })[0]!);
    const input = screen.getByPlaceholderText(/Connection name/i);
    await user.type(input, "Production OpenAI");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(mockedApi.createProviderConnection).toHaveBeenCalledWith("org_1", {
        provider_type: "openai",
        display_name: "Production OpenAI",
      });
    });
  });

  it("tests a connection", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.testProviderConnectionById.mockResolvedValue({
      connection_id: "conn_1",
      provider_type: "openai",
      health_status: "healthy",
      tested: true,
      detail: "Connection healthy.",
    });

    renderPage();
    await screen.findByText("Production OpenAI");

    await user.click(screen.getByRole("button", { name: "Test" }));

    await waitFor(() => {
      expect(mockedApi.testProviderConnectionById).toHaveBeenCalledWith("org_1", "conn_1");
    });
  });

  it("deletes a connection after confirming", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.deleteProviderConnection.mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Production OpenAI");

    await user.click(screen.getByRole("button", { name: /delete connection/i }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(mockedApi.deleteProviderConnection).toHaveBeenCalledWith("org_1", "conn_1");
    });
  });
});
