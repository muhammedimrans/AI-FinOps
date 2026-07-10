import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute";
import { useAuthStore } from "../stores/auth";

vi.mock("../services/api", () => ({
  getMe: vi.fn().mockRejectedValue(new Error("not used in these tests")),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/set-password"
          element={<ProtectedRoute>set-password-page</ProtectedRoute>}
        />
        <Route
          path="/onboarding"
          element={<ProtectedRoute>onboarding-page</ProtectedRoute>}
        />
        <Route path="/dashboard" element={<ProtectedRoute>dashboard-page</ProtectedRoute>} />
        <Route path="/login" element={<div>login-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const baseUser = {
  id: "usr_1",
  email: "ada@example.com",
  username: null,
  display_name: "Ada",
  status: "active",
  email_verified: true,
};

describe("ProtectedRoute — EP-21.3 onboarding gate", () => {
  beforeEach(() => {
    useAuthStore.getState().clearAuth();
  });

  it("redirects to /login when there is no session at all", () => {
    renderAt("/dashboard");
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("redirects an authenticated user with incomplete onboarding to /onboarding", async () => {
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });

    renderAt("/dashboard");

    await waitFor(() => expect(screen.getByText("onboarding-page")).toBeInTheDocument());
  });

  it("does not redirect a user with completed onboarding", async () => {
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: true });

    renderAt("/dashboard");

    await waitFor(() => expect(screen.getByText("dashboard-page")).toBeInTheDocument());
  });

  it("does not loop when an incomplete user is already on /onboarding", async () => {
    useAuthStore
      .getState()
      .setLogin("access.token", "refresh.token", { ...baseUser, onboarding_completed: false });

    renderAt("/onboarding");

    await waitFor(() => expect(screen.getByText("onboarding-page")).toBeInTheDocument());
  });

  it("does not force onboarding for a session with an unknown (undefined) status", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", { ...baseUser });

    renderAt("/dashboard");

    await waitFor(() => expect(screen.getByText("dashboard-page")).toBeInTheDocument());
  });
});

// EP-24.6.1 (Issue 1) — mandatory "Set Password" gate for a Google-only
// account, checked ahead of the onboarding gate above.
describe("ProtectedRoute — EP-24.6.1 set-password gate", () => {
  beforeEach(() => {
    useAuthStore.getState().clearAuth();
  });

  it("redirects an authenticated user with no password configured to /set-password", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      password_configured: false,
      onboarding_completed: false,
    });

    renderAt("/dashboard");

    await waitFor(() => expect(screen.getByText("set-password-page")).toBeInTheDocument());
  });

  it("takes priority over the onboarding gate", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      password_configured: false,
      onboarding_completed: false,
    });

    renderAt("/onboarding");

    await waitFor(() => expect(screen.getByText("set-password-page")).toBeInTheDocument());
  });

  it("does not redirect a user who already has a password configured", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      password_configured: true,
      onboarding_completed: true,
    });

    renderAt("/dashboard");

    await waitFor(() => expect(screen.getByText("dashboard-page")).toBeInTheDocument());
  });

  it("does not loop when an unconfigured user is already on /set-password", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      ...baseUser,
      password_configured: false,
    });

    renderAt("/set-password");

    await waitFor(() => expect(screen.getByText("set-password-page")).toBeInTheDocument());
  });

  it("does not force the gate for a session with an unknown (undefined) status", async () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", { ...baseUser });

    renderAt("/dashboard");

    await waitFor(() => expect(screen.getByText("dashboard-page")).toBeInTheDocument());
  });
});
