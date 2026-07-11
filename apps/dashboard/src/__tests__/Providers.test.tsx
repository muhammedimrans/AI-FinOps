import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { ProvidersResponse, ModelsResponse } from "../types/api";
import type { ProviderConnectionRecord } from "../services/api";

// features/Providers.tsx transitively imports the theme store (via
// lib/chartPalette), which reads window.matchMedia on first access —
// jsdom doesn't implement it (same workaround every other dashboard test
// file uses).
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

// EP-26.0.3.2 — Providers.tsx renders purely from UsageCostRecord
// aggregation (GET /v1/dashboard/providers), never from ProviderConnection
// rows. A validated connection to a provider with no bulk usage API
// (Google/Azure/Grok/Ollama) previously showed the exact same "No
// providers found" empty state as a genuinely disconnected org — these
// tests pin the fix: the page now distinguishes the two using the
// provider-connections list.

const { default: Providers } = await import("../features/Providers");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listProviderConnections: vi.fn(),
    getProviders: vi.fn(),
    getModels: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const EMPTY_PROVIDERS: ProvidersResponse = { providers: [], currency: "USD" };
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
      <Providers />
    </QueryClientProvider>,
  );
}

describe("Providers page — connected-but-zero-usage empty state (EP-26.0.3.2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getProviders.mockResolvedValue(EMPTY_PROVIDERS);
    mockedApi.getModels.mockResolvedValue(EMPTY_MODELS);
  });

  it("shows the generic 'no providers found' message for a truly disconnected org", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });

    renderPage();

    expect(await screen.findByText("No providers found")).toBeTruthy();
    expect(screen.getByText(/Connect a provider to get started/i)).toBeTruthy();
  });

  it("shows the honest 'connected, no spend data' state for a validated Google connection", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ provider_type: "google", display_name: "My Gemini" })],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText("Connected — no spend data yet")).toBeTruthy();
    expect(screen.getByText("My Gemini")).toBeTruthy();
    expect(screen.getByText("No usage API")).toBeTruthy();
    expect(screen.queryByText("No providers found")).toBeNull();
  });

  it("shows 'Waiting for usage' (not 'No usage API') for a usage-capable connection with zero spend yet", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ provider_type: "openai", display_name: "My OpenAI" })],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText("Connected — no spend data yet")).toBeTruthy();
    expect(screen.getByText("Waiting for usage")).toBeTruthy();
    expect(screen.queryByText("No usage API")).toBeNull();
  });
});
