import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

async function startNewChat(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText("Welcome to AI Playground");
  await user.click(screen.getByRole("button", { name: /start a new chat/i }));
}

async function sendMessage(user: ReturnType<typeof userEvent.setup>, text = "Say hello") {
  await startNewChat(user);
  const textarea = screen.getByLabelText("Message");
  await user.type(textarea, text);
  await user.click(screen.getByRole("button", { name: /^send$/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme", isPersonal: false });
  mockedApi.listPlaygroundConnections.mockResolvedValue(CONNECTIONS);
  mockedApi.listPlaygroundModels.mockResolvedValue(MODELS);
  mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
  mockedApi.listPlaygroundHistory.mockResolvedValue({ executions: [], total: 0 });
});

describe("Playground — Chat tab", () => {
  it("renders the connected provider and its live model catalog", async () => {
    renderPlayground();
    expect((await screen.findAllByText("Production OpenAI")).length).toBeGreaterThan(0);
    expect(await screen.findByText("GPT-4o")).toBeInTheDocument();
  });

  it("shows the Provider Info Card with health and capabilities", async () => {
    renderPlayground();
    await screen.findAllByText("Production OpenAI");
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(await screen.findByText("128,000 tok")).toBeInTheDocument();
  });

  it("shows the Playground homepage with suggested prompts when no chat is active", async () => {
    renderPlayground();
    expect(await screen.findByText("Welcome to AI Playground")).toBeInTheDocument();
    expect(screen.getByText("Suggested prompts")).toBeInTheDocument();
    expect(screen.getByText("Your providers")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /explain kubernetes/i })).toBeInTheDocument();
  });

  it("disables sending a prompt to a connection with no credential", async () => {
    renderPlayground();
    await screen.findAllByText("Production OpenAI");
    const option = screen.getByText(/no credential/i);
    expect(option).toBeInTheDocument();
  });

  it("starting a new chat clears the homepage and reveals the composer", async () => {
    const user = userEvent.setup();
    renderPlayground();
    await startNewChat(user);
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
    expect(screen.queryByText("Welcome to AI Playground")).not.toBeInTheDocument();
  });

  it("a suggested prompt starts a new chat and pre-fills the composer", async () => {
    const user = userEvent.setup();
    renderPlayground();
    await screen.findByText("Welcome to AI Playground");
    await user.click(screen.getByRole("button", { name: /explain kubernetes/i }));
    expect(screen.getByLabelText<HTMLTextAreaElement>("Message").value).toContain("Kubernetes");
  });

  it("sends a prompt, clears the composer, and displays the real response and stats panel", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);

    await waitFor(() =>
      expect(mockedApi.executePlayground).toHaveBeenCalledWith(
        "org_1",
        expect.objectContaining({
          provider_connection_id: "conn_1",
          model_id: "gpt-4o",
          user_prompt: "Say hello",
        }),
      ),
    );

    expect(await screen.findByText("Hello there!")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue("");
    expect(screen.getByText("Input tokens")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
  });

  it("Ctrl+Enter in the prompt editor sends the message", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await startNewChat(user);
    const textarea = screen.getByLabelText("Message");
    await user.type(textarea, "Say hello");
    await user.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(mockedApi.executePlayground).toHaveBeenCalledTimes(1));
  });

  it("shows the full response-actions row on a completed response", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);
    await screen.findByText("Hello there!");

    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Markdown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Raw JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Execution Details" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("retry re-runs the same turn in place with its own captured params", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);
    await screen.findByText("Hello there!");

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mockedApi.executePlayground).toHaveBeenCalledTimes(2));
    expect(mockedApi.executePlayground).toHaveBeenLastCalledWith(
      "org_1",
      expect.objectContaining({ user_prompt: "Say hello", model_id: "gpt-4o" }),
    );
  });

  it("View Execution Details opens the drawer with the real execution id", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);
    await screen.findByText("Hello there!");

    await user.click(screen.getByRole("button", { name: "View Execution Details" }));
    const dialog = await screen.findByRole("dialog", { name: /execution details/i });
    expect(within(dialog).getByText("pgexec_1")).toBeInTheDocument();
    expect(within(dialog).getByText("201 Created")).toBeInTheDocument();
  });

  it("opens the Cost Analysis panel on a completed response", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);
    await screen.findByText("Hello there!");

    await user.click(screen.getByRole("button", { name: /cost analysis/i }));
    expect(await screen.findByText("Largest context window")).toBeInTheDocument();
    expect(screen.getByText("Cheapest model")).toBeInTheDocument();
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
    expect(screen.queryByLabelText("Project (optional)")).not.toBeInTheDocument();
  });

  it("supports collapsing the Advanced Parameters section", async () => {
    const user = userEvent.setup();
    renderPlayground();
    await screen.findByText("GPT-4o");
    const toggle = screen.getByRole("button", { name: /advanced parameters/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Temperature")).toBeInTheDocument();
  });

  it("shows Model details for the selected model on demand", async () => {
    const user = userEvent.setup();
    renderPlayground();
    await screen.findByText("GPT-4o");
    await user.click(screen.getByRole("button", { name: /model details/i }));
    expect(screen.getByText("Input pricing")).toBeInTheDocument();
    expect(screen.getByText(/knowledge cutoff/i)).toBeInTheDocument();
  });

  it("a sent conversation appears in the sidebar grouped under Today, and New chat starts fresh", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);
    await screen.findByText("Hello there!");

    expect(await screen.findByText("Today")).toBeInTheDocument();
    expect(screen.getAllByText(/say hello/i).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /^new chat$/i }));
    expect(screen.getByText("Start a conversation")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue("");
  });

  it("updates the current-session analytics sidebar after a successful response", async () => {
    mockedApi.executePlayground.mockResolvedValue(EXECUTION);
    const user = userEvent.setup();
    renderPlayground();
    await sendMessage(user);
    await screen.findByText("Hello there!");

    expect(screen.getByText("Current session")).toBeInTheDocument();
    const requestsStat = screen.getByText("Requests").closest("div");
    expect(requestsStat).toHaveTextContent("1");
  });
});

describe("Playground — History tab", () => {
  it("lists persisted Playground executions grouped by day", async () => {
    const history: PlaygroundHistoryResponse = { executions: [EXECUTION], total: 1 };
    mockedApi.listPlaygroundHistory.mockResolvedValue(history);
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByText("Say hello")).toBeInTheDocument();
    expect(screen.getByText("Today")).toBeInTheDocument();
  });

  it("filters history by status client-side", async () => {
    const failed: PlaygroundExecutionRecord = { ...EXECUTION, id: "pgexec_2", status: "failed", error_message: "boom", user_prompt: "Broken prompt" };
    mockedApi.listPlaygroundHistory.mockResolvedValue({ executions: [EXECUTION, failed], total: 2 });
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "History" }));
    await screen.findByText("Say hello");
    expect(screen.getByText("Broken prompt")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Filter by status"), "failed");
    expect(screen.queryByText("Say hello")).not.toBeInTheDocument();
    expect(screen.getByText("Broken prompt")).toBeInTheDocument();
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

  it("deletes a history entry after confirmation", async () => {
    mockedApi.listPlaygroundHistory.mockResolvedValue({ executions: [EXECUTION], total: 1 });
    mockedApi.deletePlaygroundExecution.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "History" }));
    await screen.findByText("Say hello");
    await user.click(screen.getByLabelText("Delete"));
    const dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mockedApi.deletePlaygroundExecution).toHaveBeenCalledWith("org_1", "pgexec_1"));
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
  it("runs a comparison across two selected connections and renders side-by-side cards", async () => {
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

  it("shows a live 'sending' indicator while a comparison is running", async () => {
    let resolveCompare: (v: { comparison_group_id: string; executions: PlaygroundExecutionRecord[] }) => void = () => {};
    mockedApi.comparePlayground.mockReturnValue(
      new Promise((resolve) => {
        resolveCompare = resolve;
      }),
    );
    const user = userEvent.setup();
    renderPlayground();
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await screen.findByText("Production OpenAI");
    await user.click(screen.getAllByRole("checkbox")[0]!);
    await screen.findByLabelText(/Model for Production OpenAI/i);
    await user.selectOptions(screen.getByLabelText(/Model for Production OpenAI/i), "gpt-4o");
    await user.type(screen.getByLabelText("Comparison prompt"), "hi");
    await user.click(screen.getByRole("button", { name: /run comparison/i }));

    expect(await screen.findByText(/sending prompt to 1 provider/i)).toBeInTheDocument();
    resolveCompare({ comparison_group_id: "cmp_1", executions: [EXECUTION] });
    await waitFor(() => expect(screen.queryByText(/sending prompt to/i)).not.toBeInTheDocument());
  });
});
