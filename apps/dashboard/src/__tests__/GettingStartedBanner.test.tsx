import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";

// features/Overview.tsx transitively imports the theme store (via
// lib/chartPalette), which reads window.matchMedia on first access —
// jsdom doesn't implement it, so stub it before that import runs.
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

const { GettingStartedBanner } = await import("../features/Overview");

// EP-21.3 — "Empty Dashboard Improvements": replaces blank analytics with
// an actionable prompt when the org has no provider connections and/or no
// projects yet, reusing the same query keys the Connections/Projects pages
// already populate.

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listProviderConnections: vi.fn(),
    listProjectsCrud: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function renderBanner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <GettingStartedBanner />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GettingStartedBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
  });

  it("prompts to connect a provider when there are none", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [{ id: "proj_1" } as never], total: 1 });
    renderBanner();
    expect(await screen.findByText(/Connect your first provider/i)).toBeTruthy();
    expect(screen.queryByText(/Create your first project/i)).toBeNull();
  });

  it("prompts to create a project when there are none", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [{ id: "conn_1" } as never],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    renderBanner();
    expect(await screen.findByText(/Create your first project/i)).toBeTruthy();
    expect(screen.queryByText(/Connect your first provider/i)).toBeNull();
  });

  it("renders nothing once both a connection and a project exist", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [{ id: "conn_1" } as never],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [{ id: "proj_1" } as never], total: 1 });
    const { container } = renderBanner();
    await waitFor(() => expect(mockedApi.listProviderConnections).toHaveBeenCalled());
    await waitFor(() => expect(mockedApi.listProjectsCrud).toHaveBeenCalled());
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
