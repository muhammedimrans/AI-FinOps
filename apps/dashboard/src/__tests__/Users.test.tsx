import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Users from "../features/Users";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import * as api from "../services/api";
import type { Member, InvitationRecord } from "../services/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listMembers: vi.fn(),
    updateMemberRole: vi.fn(),
    removeMember: vi.fn(),
    listInvitations: vi.fn(),
    createInvitation: vi.fn(),
    resendInvitation: vi.fn(),
    cancelInvitation: vi.fn(),
    transferOwnership: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function member(overrides: Partial<Member> = {}): Member {
  return {
    id: "mem_1",
    user_id: "usr_1",
    email: "alice@example.com",
    display_name: "Alice",
    role: "member",
    status: "active",
    created_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

function invitation(overrides: Partial<InvitationRecord> = {}): InvitationRecord {
  return {
    id: "inv_1",
    organization_id: "org_1",
    email: "bob@example.com",
    role: "member",
    status: "pending",
    invited_by_name: "Alice",
    invited_by_email: "alice@example.com",
    created_at: "2026-07-01T00:00:00Z",
    expires_at: "2026-07-08T00:00:00Z",
    accepted_at: null,
    cancelled_at: null,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Users />
    </QueryClientProvider>,
  );
}

describe("Users (Members) page — EP-24.6", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    useAuthStore.setState({
      user: {
        id: "usr_owner",
        email: "owner@example.com",
        username: null,
        display_name: "Owner",
        status: "active",
        email_verified: true,
      },
    } as Partial<ReturnType<typeof useAuthStore.getState>>);
  });

  it("renders members and pending invitations", async () => {
    mockedApi.listMembers.mockResolvedValue({
      members: [member({ role: "owner", email: "owner@example.com", display_name: "Owner" })],
      total: 1,
    });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [invitation()], total: 1 });

    renderPage();

    expect(await screen.findByText("owner@example.com")).toBeTruthy();
    expect(screen.getByText("bob@example.com")).toBeTruthy();
    expect(screen.getByText("Pending")).toBeTruthy();
  });

  it("shows an empty state when there are no pending invitations", async () => {
    mockedApi.listMembers.mockResolvedValue({ members: [member()], total: 1 });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [], total: 0 });

    renderPage();

    expect(
      await screen.findByText(
        "Every invitation you send will show up here until it's accepted, declined, or expires.",
      ),
    ).toBeTruthy();
  });

  it("sends an invitation via the modal", async () => {
    mockedApi.listMembers.mockResolvedValue({ members: [member()], total: 1 });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [], total: 0 });
    mockedApi.createInvitation.mockResolvedValue(invitation({ email: "new@example.com" }));

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("alice@example.com");
    await user.click(screen.getByRole("button", { name: /invite member/i }));
    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.click(screen.getByRole("button", { name: /send invitation/i }));

    await waitFor(() => {
      expect(mockedApi.createInvitation).toHaveBeenCalledWith("org_1", "new@example.com", "member");
    });
  });

  it("resends an invitation", async () => {
    mockedApi.listMembers.mockResolvedValue({ members: [member()], total: 1 });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [invitation()], total: 1 });
    mockedApi.resendInvitation.mockResolvedValue({ message: "ok" });

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("bob@example.com");
    await user.click(screen.getByRole("button", { name: /resend invitation to bob@example.com/i }));

    await waitFor(() => {
      expect(mockedApi.resendInvitation).toHaveBeenCalledWith("inv_1");
    });
  });

  it("cancels an invitation via confirm dialog", async () => {
    mockedApi.listMembers.mockResolvedValue({ members: [member()], total: 1 });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [invitation()], total: 1 });
    mockedApi.cancelInvitation.mockResolvedValue({ message: "ok" });

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("bob@example.com");
    await user.click(screen.getByRole("button", { name: /cancel invitation to bob@example.com/i }));
    await user.click(screen.getByRole("button", { name: /^cancel invitation$/i }));

    await waitFor(() => {
      expect(mockedApi.cancelInvitation).toHaveBeenCalledWith("inv_1");
    });
  });

  it("changes a member's role", async () => {
    mockedApi.listMembers.mockResolvedValue({
      members: [member(), member({ id: "mem_2", email: "carol@example.com", display_name: "Carol" })],
      total: 2,
    });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [], total: 0 });
    mockedApi.updateMemberRole.mockResolvedValue(
      member({ id: "mem_2", email: "carol@example.com", role: "admin" }),
    );

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("carol@example.com");
    await user.selectOptions(screen.getByLabelText("Change role for carol@example.com"), "admin");

    await waitFor(() => {
      expect(mockedApi.updateMemberRole).toHaveBeenCalledWith("org_1", "mem_2", "admin");
    });
  });

  it("removes a member via confirm dialog", async () => {
    mockedApi.listMembers.mockResolvedValue({
      members: [member(), member({ id: "mem_2", email: "carol@example.com", display_name: "Carol" })],
      total: 2,
    });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [], total: 0 });
    mockedApi.removeMember.mockResolvedValue(undefined);

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("carol@example.com");
    await user.click(screen.getByRole("button", { name: /remove carol@example.com/i }));
    await user.click(screen.getByRole("button", { name: /^remove$/i }));

    await waitFor(() => {
      expect(mockedApi.removeMember).toHaveBeenCalledWith("org_1", "mem_2");
    });
  });

  it("shows a transfer-ownership action for other members when the caller is owner", async () => {
    mockedApi.listMembers.mockResolvedValue({
      members: [
        member({ id: "mem_owner", email: "owner@example.com", display_name: "Owner", role: "owner" }),
        member({ id: "mem_2", email: "carol@example.com", display_name: "Carol", role: "admin" }),
      ],
      total: 2,
    });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [], total: 0 });
    mockedApi.transferOwnership.mockResolvedValue(
      member({ id: "mem_2", email: "carol@example.com", role: "owner" }),
    );

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("carol@example.com");
    await user.click(screen.getByRole("button", { name: /transfer ownership to carol@example.com/i }));
    await user.click(screen.getByRole("button", { name: /^transfer ownership$/i }));

    await waitFor(() => {
      expect(mockedApi.transferOwnership).toHaveBeenCalledWith("org_1", "mem_2");
    });
  });

  it("does not show a transfer-ownership action when the caller is not owner", async () => {
    useAuthStore.setState({
      user: {
        id: "usr_admin",
        email: "admin@example.com",
        username: null,
        display_name: "Admin",
        status: "active",
        email_verified: true,
      },
    } as Partial<ReturnType<typeof useAuthStore.getState>>);
    mockedApi.listMembers.mockResolvedValue({
      members: [
        member({ id: "mem_owner", email: "owner@example.com", role: "owner" }),
        member({ id: "mem_admin", email: "admin@example.com", role: "admin" }),
      ],
      total: 2,
    });
    mockedApi.listInvitations.mockResolvedValue({ invitations: [], total: 0 });

    renderPage();

    await screen.findByText("owner@example.com");
    expect(screen.queryByRole("button", { name: /make owner/i })).toBeNull();
  });
});
