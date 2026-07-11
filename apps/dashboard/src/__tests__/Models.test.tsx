import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { ModelsResponse } from "../types/api";
import type { ProviderConnectionRecord } from "../services/api";

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

// EP-26.0.3.2 — Models.tsx shows models *with recorded usage* (a
// UsageCostRecord-derived leaderboard, by design — not a raw
// model-discovery catalog). A connected provider with no usage API
// (Google/Azure/Grok/Ollama) correctly shows zero rows, but the empty
// state must say so honestly instead of a bare "No models found".

const { default: Models } = await import("../features/Models");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listProviderConnections: vi.fn(),
    getModels: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const EMPTY_MODELS: ModelsResponse = { models: [], currency: "USD" };

function connection(overrides: Partial<ProviderConnectionRecord> = {}): ProviderConnectionRecord {
  return {
    id: "conn_1",
    provider_type: "google",
    display_name: "My Gemini",
    project_id: null,
    is_active: true,
    has_credential: true,
    masked_api_key: "AIza***xyz",
    base_url: null,
    health_status: "healthy",
    last_validation_status: "healthy",
    last_error: null,
    last_failure_at: null,
    last_recovery_at: null,
    consecutive_failure_count: 0,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Models />
    </QueryClientProvider>,
  );
}

describe("Models page — honest empty states (EP-26.0.3.2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getModels.mockResolvedValue(EMPTY_MODELS);
  });

  it("shows 'Connect a provider' for a truly disconnected org", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });

    renderPage();

    expect(await screen.findByText("No models found")).toBeTruthy();
    expect(screen.getByText(/Connect a provider to get started/i)).toBeTruthy();
  });

  it("explains the no-usage-API limitation when every connection lacks one", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ provider_type: "google" })],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText("No models with recorded usage yet")).toBeTruthy();
    expect(screen.getByText(/don't expose a bulk usage-history API/i)).toBeTruthy();
    expect(screen.queryByText("No models found")).toBeNull();
  });

  it("shows a 'will appear once usage is reported' message for a usage-capable connection", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ provider_type: "openai" })],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText("No models with recorded usage yet")).toBeTruthy();
    expect(screen.getByText(/will appear here once your connected providers report usage/i)).toBeTruthy();
  });
});
