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
  SchedulerStatusResponse,
  SyncStatusResponse,
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
    rotateProviderConnectionKey: vi.fn(),
    getProviderConnectionSyncStatus: vi.fn(),
    syncProviderConnection: vi.fn(),
    syncAllProviderConnections: vi.fn(),
    getSchedulerStatus: vi.fn(),
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
  has_credential: false,
  masked_api_key: null,
  base_url: null,
  health_status: "unknown",
  last_validation_status: null,
  last_error: null,
  last_failure_at: null,
  last_recovery_at: null,
  consecutive_failure_count: 0,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const NEVER_SYNCED_STATUS: SyncStatusResponse = {
  connection_id: "conn_1",
  provider_type: "openai",
  sync_status: "never_synced",
  last_sync_started_at: null,
  last_sync_completed_at: null,
  last_successful_sync_at: null,
  last_error: null,
  last_imported_at: null,
  records_imported: 0,
  tokens_imported: 0,
  estimated_cost_imported: [],
  supports_usage_sync: true,
};

const DISABLED_SCHEDULER_STATUS: SchedulerStatusResponse = {
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
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue(NEVER_SYNCED_STATUS);
    mockedApi.getSchedulerStatus.mockResolvedValue(DISABLED_SCHEDULER_STATUS);
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
      last_validation_status: "healthy",
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

  it("shows the masked key, not the plaintext, for a connection with a credential", async () => {
    const withKey: ProviderConnectionRecord = {
      ...SAMPLE_CONNECTION,
      has_credential: true,
      masked_api_key: "sk-********************************AbC",
    };
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [withKey], total: 1 });
    renderPage();
    expect(await screen.findByText("sk-********************************AbC")).toBeTruthy();
  });

  it("shows last validation status and error message when present", async () => {
    const failed: ProviderConnectionRecord = {
      ...SAMPLE_CONNECTION,
      health_status: "critical",
      last_validation_status: "invalid_api_key",
      last_error: "The API key is invalid or has been revoked.",
      last_failure_at: "2026-07-01T00:00:00Z",
    };
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [failed], total: 1 });
    renderPage();
    await screen.findByText("Production OpenAI");
    expect(screen.getByText("Invalid API key")).toBeTruthy();
    expect(screen.getByText("The API key is invalid or has been revoked.")).toBeTruthy();
  });

  it("creates a connection with an API key, masked by default with a reveal toggle", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.createProviderConnection.mockResolvedValue({
      ...SAMPLE_CONNECTION,
      has_credential: true,
      last_validation_status: "healthy",
    });

    renderPage();
    await screen.findByText(/No provider connections yet/i);

    await user.click(screen.getAllByRole("button", { name: /add provider/i })[0]!);
    await user.type(screen.getByPlaceholderText(/Connection name/i), "Production OpenAI");

    const keyInput = screen.getByPlaceholderText("API key (sk-...)");
    expect(keyInput.getAttribute("type")).toBe("password");
    await user.click(screen.getByLabelText("Reveal API key"));
    expect(keyInput.getAttribute("type")).toBe("text");
    await user.type(keyInput, "sk-" + "a".repeat(40));

    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(mockedApi.createProviderConnection).toHaveBeenCalledWith("org_1", {
        provider_type: "openai",
        display_name: "Production OpenAI",
        api_key: "sk-" + "a".repeat(40),
      });
    });
  });

  it("rotates a connection's API key", async () => {
    const user = userEvent.setup();
    const withKey: ProviderConnectionRecord = {
      ...SAMPLE_CONNECTION,
      has_credential: true,
      masked_api_key: "sk-********************************AbC",
    };
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [withKey], total: 1 });
    mockedApi.rotateProviderConnectionKey.mockResolvedValue({
      ...withKey,
      last_validation_status: "healthy",
    });

    renderPage();
    await screen.findByText("Production OpenAI");

    await user.click(screen.getByRole("button", { name: /rotate key/i }));
    const newKeyInput = screen.getByPlaceholderText("New API key");
    await user.type(newKeyInput, "sk-" + "newnew".repeat(6));
    await user.click(screen.getByRole("button", { name: /save & validate/i }));

    await waitFor(() => {
      expect(mockedApi.rotateProviderConnectionKey).toHaveBeenCalledWith(
        "org_1",
        "conn_1",
        "sk-" + "newnew".repeat(6),
      );
    });
  });
});

describe("Connections page — usage synchronization (EP-23.3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getProviderInfo.mockResolvedValue(SAMPLE_INFO);
    mockedApi.getSchedulerStatus.mockResolvedValue(DISABLED_SCHEDULER_STATUS);
  });

  it("shows 'never synced' for a connection that has not been synced yet", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue(NEVER_SYNCED_STATUS);

    renderPage();
    await screen.findByText("Production OpenAI");

    expect(await screen.findByText("Never synced")).toBeTruthy();
  });

  it("shows sync status, records/tokens imported, and estimated cost after a successful sync", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue({
      ...NEVER_SYNCED_STATUS,
      sync_status: "success",
      last_sync_completed_at: "2026-07-01T00:00:00Z",
      records_imported: 128,
      tokens_imported: 45210,
      estimated_cost_imported: [{ currency: "USD", total_cost: "1.23", record_count: 128 }],
    });

    renderPage();
    await screen.findByText("Production OpenAI");

    expect(await screen.findByText("Synced")).toBeTruthy();
    expect(screen.getByText(/128 records imported/)).toBeTruthy();
    expect(screen.getByText(/45,210 tokens imported/)).toBeTruthy();
    expect(screen.getByText(/estimated cost imported/)).toBeTruthy();
  });

  it("shows the last error when the most recent sync failed", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue({
      ...NEVER_SYNCED_STATUS,
      sync_status: "failed",
      last_error: "Could not reach the provider — network error.",
    });

    renderPage();
    await screen.findByText("Production OpenAI");

    expect(await screen.findByText("Sync failed")).toBeTruthy();
    expect(screen.getByText("Could not reach the provider — network error.")).toBeTruthy();
  });

  it("triggers a manual sync via 'Sync now' and shows the updated status", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue(NEVER_SYNCED_STATUS);
    mockedApi.syncProviderConnection.mockResolvedValue({
      run: {
        run_id: "run_1",
        connection_id: "conn_1",
        provider_type: "openai",
        status: "completed",
        started_at: "2026-07-01T00:00:00Z",
        completed_at: "2026-07-01T00:01:00Z",
        records_imported: 10,
        records_failed: 0,
        error_message: null,
      },
      sync_status: {
        ...NEVER_SYNCED_STATUS,
        sync_status: "success",
        records_imported: 10,
        tokens_imported: 500,
      },
    });

    renderPage();
    await screen.findByText("Production OpenAI");

    await user.click(screen.getByRole("button", { name: /sync now/i }));

    await waitFor(() => {
      expect(mockedApi.syncProviderConnection).toHaveBeenCalledWith("org_1", "conn_1");
    });
    expect(await screen.findByText("Synced")).toBeTruthy();
    expect(screen.getByText(/10 records imported/)).toBeTruthy();
  });

  it("disables 'Sync now' for a provider that does not support usage sync yet", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue({
      ...NEVER_SYNCED_STATUS,
      supports_usage_sync: false,
    });

    renderPage();
    await screen.findByText("Production OpenAI");
    await screen.findByText(/isn't available for this provider yet/i);

    const syncButton = screen.getByRole("button", { name: /sync now/i });
    expect(syncButton).toBeDisabled();
  });

  it("refreshes sync status via 'Refresh status'", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue(NEVER_SYNCED_STATUS);

    renderPage();
    await screen.findByText("Production OpenAI");

    await user.click(screen.getByRole("button", { name: /refresh status/i }));

    await waitFor(() => {
      expect(mockedApi.getProviderConnectionSyncStatus).toHaveBeenCalledTimes(2);
    });
  });

  it("triggers 'Sync all' for every active connection", async () => {
    const user = userEvent.setup();
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [SAMPLE_CONNECTION],
      total: 1,
    });
    mockedApi.getProviderConnectionSyncStatus.mockResolvedValue(NEVER_SYNCED_STATUS);
    mockedApi.syncAllProviderConnections.mockResolvedValue({
      runs: [],
      total: 1,
      succeeded: 1,
      failed: 0,
    });

    renderPage();
    await screen.findByText("Production OpenAI");

    await user.click(screen.getByRole("button", { name: /sync all/i }));

    await waitFor(() => {
      expect(mockedApi.syncAllProviderConnections).toHaveBeenCalledWith("org_1");
    });
  });

  it("does not show 'Sync all' when there are no connections", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    renderPage();
    await screen.findByText(/No provider connections yet/i);
    expect(screen.queryByRole("button", { name: /sync all/i })).toBeNull();
  });
});

describe("Connections page — automatic sync status (EP-23.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getProviderInfo.mockResolvedValue(SAMPLE_INFO);
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
  });

  it("shows disabled state when auto sync is off", async () => {
    mockedApi.getSchedulerStatus.mockResolvedValue(DISABLED_SCHEDULER_STATUS);
    renderPage();
    expect(await screen.findByText("Disabled")).toBeTruthy();
    expect(screen.getByText(/last sync never/i)).toBeTruthy();
  });

  it("shows enabled state with interval, next sync, and scheduler health", async () => {
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
        completed_jobs: 5,
        failed_jobs: 0,
        average_duration_seconds: 2.5,
        last_execution: "2026-07-01T00:00:00Z",
      },
    });
    renderPage();

    expect(await screen.findByText("Enabled")).toBeTruthy();
    expect(screen.getByText(/every 15m/i)).toBeTruthy();
    expect(screen.getByText(/next sync/i)).toBeTruthy();
    expect(screen.getByText(/scheduler healthy/i)).toBeTruthy();
  });

  it("shows the current job's status, records imported, and duration", async () => {
    mockedApi.getSchedulerStatus.mockResolvedValue({
      organization_id: "org_1",
      auto_sync_enabled: true,
      interval: "1h",
      interval_seconds: 3600,
      last_sync_at: null,
      last_sync_status: null,
      next_sync_at: "2026-07-01T01:00:00Z",
      current_job: {
        job_id: "job_1",
        organization_id: "org_1",
        status: "running",
        queued_at: "2026-07-01T00:00:00Z",
        started_at: "2026-07-01T00:00:01Z",
        completed_at: null,
        connections_synced: 0,
        connections_failed: 0,
        records_imported: 12,
        retry_count: 1,
        duration_seconds: 3.4,
        error: null,
      },
      scheduler_health: "healthy",
      monitoring: {
        is_running: true,
        active_jobs: 1,
        queued_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        average_duration_seconds: null,
        last_execution: null,
      },
    });
    renderPage();

    expect(await screen.findByText("Running")).toBeTruthy();
    expect(screen.getByText(/12 records/)).toBeTruthy();
    expect(screen.getByText(/3\.4s/)).toBeTruthy();
    expect(screen.getByText(/retry 1/)).toBeTruthy();
  });
});
