import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import * as api from "../services/api";

// features/SetPassword.tsx renders AuthShell -> ThemeSwitcher, which reads
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

const { default: SetPassword } = await import("../features/SetPassword");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    setPassword: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function setGoogleOnlyUser() {
  useAuthStore.getState().setLogin("access.token", "refresh.token", {
    id: "usr_1",
    email: "ada@example.com",
    username: null,
    display_name: "Ada",
    status: "active",
    email_verified: true,
    password_configured: false,
  });
}

function renderSetPassword(path = "/set-password") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/set-password" element={<SetPassword />} />
        <Route path="/onboarding" element={<div>onboarding-page</div>} />
        <Route path="/dashboard" element={<div>dashboard-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SetPassword — EP-24.6.1", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearAuth();
  });

  it("shows a validation error for a password under 8 characters", async () => {
    setGoogleOnlyUser();
    const user = userEvent.setup();
    renderSetPassword();

    await user.type(screen.getByLabelText(/^password$/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /set password/i }));

    expect(await screen.findByText(/at least 8 characters/i)).toBeTruthy();
    expect(mockedApi.setPassword).not.toHaveBeenCalled();
  });

  it("shows a validation error when the passwords don't match", async () => {
    setGoogleOnlyUser();
    const user = userEvent.setup();
    renderSetPassword();

    await user.type(screen.getByLabelText(/^password$/i), "correct-horse-battery");
    await user.type(screen.getByLabelText(/confirm password/i), "different-password");
    await user.click(screen.getByRole("button", { name: /set password/i }));

    expect(await screen.findByText(/don't match/i)).toBeTruthy();
    expect(mockedApi.setPassword).not.toHaveBeenCalled();
  });

  it("calls setPassword and navigates to /onboarding on success", async () => {
    setGoogleOnlyUser();
    mockedApi.setPassword.mockResolvedValue({
      id: "usr_1",
      email: "ada@example.com",
      username: null,
      display_name: "Ada",
      status: "active",
      email_verified: true,
      onboarding_completed: false,
      avatar_url: null,
      bio: null,
      timezone: null,
      created_at: "2026-01-01T00:00:00Z",
      preferences: {},
      google_linked: true,
      google_email: "ada@example.com",
      last_login_provider: "google",
      password_configured: true,
    });
    const user = userEvent.setup();
    renderSetPassword();

    await user.type(screen.getByLabelText(/^password$/i), "correct-horse-battery");
    await user.type(screen.getByLabelText(/confirm password/i), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /set password/i }));

    await waitFor(() => {
      expect(mockedApi.setPassword).toHaveBeenCalledWith("correct-horse-battery");
    });
    expect(await screen.findByText("onboarding-page")).toBeTruthy();
    expect(useAuthStore.getState().user?.password_configured).toBe(true);
  });

  it("does not render the form for a user who already has a password configured", () => {
    useAuthStore.getState().setLogin("access.token", "refresh.token", {
      id: "usr_1",
      email: "ada@example.com",
      username: null,
      display_name: "Ada",
      status: "active",
      email_verified: true,
      password_configured: true,
    });

    renderSetPassword();

    expect(screen.queryByLabelText(/^password$/i)).toBeNull();
  });
});
