import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../services/api";
import { useAuthStore } from "../stores/auth";

// features/AcceptInvite.tsx renders AuthShell -> ThemeSwitcher, which reads
// the theme store, which reads window.matchMedia on first access — jsdom
// doesn't implement it (same pattern as VerifyEmail.test.tsx).
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

const { default: AcceptInvite } = await import("../features/AcceptInvite");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    acceptInvitation: vi.fn(),
    declineInvitation: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/accept-invite" element={<AcceptInvite />} />
      </Routes>
    </MemoryRouter>,
  );
}

function setAuthenticated(authenticated: boolean) {
  useAuthStore.setState({
    accessToken: authenticated ? "token" : null,
    user: authenticated
      ? {
          id: "usr_1",
          email: "invitee@example.com",
          username: null,
          display_name: "Invitee",
          status: "active",
          email_verified: true,
        }
      : null,
  } as Partial<ReturnType<typeof useAuthStore.getState>>);
}

describe("AcceptInvite — EP-24.6", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuthenticated(false);
  });

  it("shows an invalid-link message when there's no token", () => {
    renderAt("/accept-invite");
    expect(screen.getByText(/invalid invitation link/i)).toBeTruthy();
  });

  it("shows a sign-in link (preserving the token) when unauthenticated", () => {
    renderAt("/accept-invite?token=raw-token");
    const link = screen.getByRole("link", { name: /sign in to accept/i });
    expect(link.getAttribute("href")).toContain("redirect=");
    expect(decodeURIComponent(link.getAttribute("href") ?? "")).toContain(
      "/accept-invite?token=raw-token",
    );
  });

  it("unauthenticated visitor can still decline", async () => {
    mockedApi.declineInvitation.mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    renderAt("/accept-invite?token=raw-token");

    await user.click(screen.getByRole("button", { name: /decline/i }));

    await waitFor(() => {
      expect(mockedApi.declineInvitation).toHaveBeenCalledWith("raw-token");
    });
    expect(await screen.findByText(/invitation declined/i)).toBeTruthy();
  });

  it("authenticated visitor can accept, showing the joined organization", async () => {
    setAuthenticated(true);
    mockedApi.acceptInvitation.mockResolvedValue({
      organization_id: "org_1",
      organization_name: "Acme",
      role: "member",
    });
    const user = userEvent.setup();
    renderAt("/accept-invite?token=raw-token");

    await user.click(screen.getByRole("button", { name: /accept invitation/i }));

    expect(await screen.findByText(/you've joined acme/i)).toBeTruthy();
    expect(mockedApi.acceptInvitation).toHaveBeenCalledWith("raw-token");
  });

  it("authenticated visitor sees an error for an invalid/expired token", async () => {
    setAuthenticated(true);
    const { ApiError } = await import("../services/api");
    mockedApi.acceptInvitation.mockRejectedValue(new ApiError(400, "This invitation is invalid or has expired."));
    const user = userEvent.setup();
    renderAt("/accept-invite?token=bad-token");

    await user.click(screen.getByRole("button", { name: /accept invitation/i }));

    expect(await screen.findByText(/this invitation is invalid or has expired/i)).toBeTruthy();
  });

  it("authenticated visitor can still decline instead of accepting", async () => {
    setAuthenticated(true);
    mockedApi.declineInvitation.mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    renderAt("/accept-invite?token=raw-token");

    await user.click(screen.getByRole("button", { name: /^decline$/i }));

    await waitFor(() => {
      expect(mockedApi.declineInvitation).toHaveBeenCalledWith("raw-token");
    });
    expect(mockedApi.acceptInvitation).not.toHaveBeenCalled();
  });
});
