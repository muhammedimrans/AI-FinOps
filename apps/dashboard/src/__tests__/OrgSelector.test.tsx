import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, getOrganizations: vi.fn() };
});

const mockedApi = vi.mocked(api);

const { default: OrgSelector } = await import("../components/OrgSelector");

function personalOrg(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "org_personal",
    name: "Ada's Workspace",
    slug: "ada-workspace",
    role: "owner",
    is_personal: true,
    ...overrides,
  };
}

function businessOrg(id: string, name: string) {
  return { id, name, slug: name.toLowerCase(), role: "owner", is_personal: false };
}

describe("OrgSelector — EP-25.1 hides the personal workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.getState().clearOrganization();
  });

  it("auto-selects the personal org silently when it's the only workspace", async () => {
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [personalOrg()],
    });
    render(<OrgSelector />);

    await waitFor(() => expect(useOrgStore.getState().organizationId).toBe("org_personal"));
    expect(useOrgStore.getState().isPersonal).toBe(true);
    // Never rendered as a pickable option.
    expect(screen.queryByText("Select organization")).toBeNull();
  });

  it("auto-selects the sole business org, never offering the hidden personal one", async () => {
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [personalOrg(), businessOrg("org_biz", "Acme Inc")],
    });
    render(<OrgSelector />);

    await waitFor(() => expect(useOrgStore.getState().organizationId).toBe("org_biz"));
    expect(useOrgStore.getState().isPersonal).toBe(false);
  });

  it("shows a picker of only business orgs when there are multiple", async () => {
    mockedApi.getOrganizations.mockResolvedValue({
      organizations: [
        personalOrg(),
        businessOrg("org_a", "Acme Inc"),
        businessOrg("org_b", "Widget Co"),
      ],
    });
    render(<OrgSelector />);

    expect(await screen.findByText("Select organization")).toBeTruthy();
    expect(screen.getByText("Acme Inc")).toBeTruthy();
    expect(screen.getByText("Widget Co")).toBeTruthy();
    expect(screen.queryByText("Ada's Workspace")).toBeNull();
  });
});
