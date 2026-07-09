import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Projects from "../features/Projects";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { ProjectRecord, ProjectsCrudListResponse } from "../services/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    getProjects: vi.fn(),
    listProjectsCrud: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const SAMPLE_PROJECT: ProjectRecord = {
  id: "proj_1",
  name: "Marketing Bot",
  description: null,
  environment: "production",
  budget: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Projects />
    </QueryClientProvider>,
  );
}

describe("Projects page — Manage projects (EP-23)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getProjects.mockResolvedValue({ projects: [], currency: "USD" });
  });

  it("shows the empty state when there are no projects", async () => {
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    renderPage();
    expect(await screen.findByText(/No projects yet/i)).toBeTruthy();
  });

  it("lists projects with their environment badge", async () => {
    const list: ProjectsCrudListResponse = { projects: [SAMPLE_PROJECT], total: 1 };
    mockedApi.listProjectsCrud.mockResolvedValue(list);
    renderPage();
    expect(await screen.findByText("Marketing Bot")).toBeTruthy();
    expect(screen.getByText("production")).toBeTruthy();
  });

  it("creates a project via the inline form", async () => {
    const user = userEvent.setup();
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.createProject.mockResolvedValue(SAMPLE_PROJECT);

    renderPage();
    await screen.findByText(/No projects yet/i);

    await user.click(screen.getByRole("button", { name: /new project/i }));
    const input = screen.getByPlaceholderText("Project name");
    await user.type(input, "Marketing Bot");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(mockedApi.createProject).toHaveBeenCalledWith("org_1", {
        name: "Marketing Bot",
        environment: "production",
      });
    });
  });

  it("renames a project inline", async () => {
    const user = userEvent.setup();
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [SAMPLE_PROJECT], total: 1 });
    mockedApi.updateProject.mockResolvedValue({ ...SAMPLE_PROJECT, name: "Renamed" });

    renderPage();
    await screen.findByText("Marketing Bot");

    await user.click(screen.getByRole("button", { name: /rename project/i }));
    const input = screen.getByDisplayValue("Marketing Bot");
    await user.clear(input);
    await user.type(input, "Renamed");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mockedApi.updateProject).toHaveBeenCalledWith("org_1", "proj_1", { name: "Renamed" });
    });
  });

  it("deletes a project after confirming", async () => {
    const user = userEvent.setup();
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [SAMPLE_PROJECT], total: 1 });
    mockedApi.deleteProject.mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Marketing Bot");

    await user.click(screen.getByRole("button", { name: /delete project/i }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(mockedApi.deleteProject).toHaveBeenCalledWith("org_1", "proj_1");
    });
  });
});
