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
