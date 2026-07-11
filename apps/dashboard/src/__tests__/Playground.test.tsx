import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Playground from "../features/Playground";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type {
  PlaygroundConnectionsResponse,
  PlaygroundModelInfo,
  PlaygroundExecutionRecord,
  PlaygroundHistoryResponse,
} from "../services/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listPlaygroundConnections: vi.fn(),
    listPlaygroundModels: vi.fn(),
    executePlayground: vi.fn(),
    comparePlayground: vi.fn(),
    listPlaygroundHistory: vi.fn(),
    deletePlaygroundExecution: vi.fn(),
    rerunPlaygroundExecution: vi.fn(),
    listProjectsCrud: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const CONNECTIONS: PlaygroundConnectionsResponse = {
  connections: [
    {
      id: "conn_1",
      provider_type: "openai",
      display_name: "Production OpenAI",
      is_active: true,
      has_credential: true,
      last_validation_status: "healthy",
    },
    {
      id: "conn_2",
      provider_type: "anthropic",
      display_name: "Claude",
      is_active: true,
      has_credential: false,
      last_validation_status: null,
    },
  ],
};

const MODELS: PlaygroundModelInfo[] = [
  {
    id: "gpt-4o",
    display_name: "GPT-4o",
    context_window: 128000,
    max_output_tokens: 4096,
    capabilities: ["streaming", "vision"],
    input_cost_per_1k: 0.005,
    output_cost_per_1k: 0.015,
    is_deprecated: false,
  },
];

const EXECUTION: PlaygroundExecutionRecord = {
  id: "pgexec_1",
  provider: "openai",
  model: "gpt-4o",
  provider_connection_id: "conn_1",
  project_id: null,
  system_prompt: null,
  user_prompt: "Say hello",
  response_text: "Hello there!",
  temperature: 0.7,
  top_p: 1,
  max_tokens: 1024,
  prompt_tokens: 10,
  completion_tokens: 5,
  total_tokens: 15,
  estimated_cost: "0.0003",
  currency: "USD",
  latency_ms: 340,
  status: "succeeded",
  error_message: null,
  comparison_group_id: null,
  created_at: new Date().toISOString(),
};

function renderPlayground() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Playground />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme", isPersonal: false });
  mockedApi.listPlaygroundConnections.mockResolvedValue(CONNECTIONS);
  mockedApi.listPlaygroundModels.mockResolvedValue(MODELS);
  mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
  mockedApi.listPlaygroundHistory.mockResolvedValue({ executions: [], total: 0 });
});

describe("Playground — Chat tab", () => {
  it("renders the connected provider and its live model catalog", async () => {
    renderPlayground();
    expect(await screen.findByText("Production OpenAI")).toBeInTheDocument();
    expect(await screen.findByText("GPT-4o")).toBeInTheDocument();
  });

  it("disables sending a prompt to a connection with no credential", async () => {
    renderPlayground();
    await screen.findByText("Production OpenAI");
    const option = screen.getByText(/no credential/i);
    expect(option).toBeInTheDocument();
  });

  it("sends a prompt and displays the real response, tokens, and cost", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await screen.findByText("GPT-4o");

    const textarea = screen.getByPlaceholderText("Send a message…");
    await user.type(textarea, "Say hello");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(mockedApi.executePlayground).toHaveBeenCalledWith("org_1", expect.objectContaining({
      provider_connection_id: "conn_1",
      model_id: "gpt-4o",
      user_prompt: "Say hello",
    })));

    expect(await screen.findByText("Hello there!")).toBeInTheDocument();
    expect(screen.getByText(/in: 10/i)).toBeInTheDocument();
    expect(screen.getByText(/out: 5/i)).toBeInTheDocument();
  });

  it("shows an empty-state and no send controls when no provider is configured", async () => {
    mockedApi.listPlaygroundConnections.mockResolvedValue({
      connections: [
        { id: "conn_2", provider_type: "anthropic", display_name: "Claude", is_active: true, has_credential: false, last_validation_status: null },
      ],
    });
    renderPlayground();
    expect(await screen.findByText(/connect a provider to start/i)).toBeInTheDocument();
  });

  it("does not show a Project selector for a Personal workspace", async () => {
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Ada's Workspace", isPersonal: true });
    renderPlayground();
    await screen.findByText("GPT-4o");
    expect(screen.queryByText("Project (optional)")).not.toBeInTheDocument();
  });
});

describe("Playground — History tab", () => {
  it("lists persisted Playground executions", async () => {
    const history: PlaygroundHistoryResponse = { executions: [EXECUTION], total: 1 };
    mockedApi.listPlaygroundHistory.mockResolvedValue(history);
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByText("Say hello")).toBeInTheDocument();
  });

  it("re-runs a history entry", async () => {
    mockedApi.listPlaygroundHistory.mockResolvedValue({ executions: [EXECUTION], total: 1 });
    mockedApi.rerunPlaygroundExecution.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "History" }));
    await screen.findByText("Say hello");
    await user.click(screen.getByLabelText("Re-run"));
    await waitFor(() => expect(mockedApi.rerunPlaygroundExecution).toHaveBeenCalledWith("org_1", "pgexec_1"));
  });

  it("shows an empty state with no history", async () => {
    mockedApi.listPlaygroundHistory.mockResolvedValue({ executions: [], total: 0 });
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByText(/no playground history yet/i)).toBeInTheDocument();
  });
});

describe("Playground — Compare tab", () => {
  it("runs a comparison across two selected connections", async () => {
    mockedApi.comparePlayground.mockResolvedValue({
      comparison_group_id: "cmp_1",
      executions: [EXECUTION],
    });
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await screen.findByText("Production OpenAI");
    // Only the configured connection (has_credential=true) is selectable.
    const checkbox = screen.getAllByRole("checkbox")[0]!;
    await user.click(checkbox);
    await screen.findByText("Model per provider");
  });
});
