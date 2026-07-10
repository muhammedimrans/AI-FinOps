import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../services/api";
import { useAuthStore } from "../stores/auth";

// features/Login.tsx renders ThemeSwitcher, which reads the theme store,
// which reads window.matchMedia on first access — jsdom doesn't implement
// it (same pattern as VerifyEmail.test.tsx / Settings.test.tsx).
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

const { default: Login } = await import("../features/Login");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    login: vi.fn(),
    getOrganizations: vi.fn(),
    resendVerification: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  );
}

async function submitLoginForm(email = "ada@example.com", password = "correct-horse-battery-staple") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email address/i), email);
  await user.type(screen.getByLabelText(/^password$/i), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

// EP-24.4.1 — regression coverage for the dashboard's login-rejected UX:
// a 403 "please verify your email" response must show the exact backend
// message plus a resend affordance, distinct from a plain 401/disabled/429
// rejection, and must never fall through to setLogin()/navigate().
describe("Login — EP-24.4.1 email verification enforcement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
    } as Partial<ReturnType<typeof useAuthStore.getState>>);
  });

  it("shows the backend's verify-email message and a resend button on 403 unverified", async () => {
    const { ApiError } = await import("../services/api");
    mockedApi.login.mockRejectedValue(
      new ApiError(403, "Please verify your email before signing in."),
    );

    renderLogin();
    await submitLoginForm();

    expect(await screen.findByText("Please verify your email before signing in.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /resend verification email/i })).toBeTruthy();
    expect(mockedApi.getOrganizations).not.toHaveBeenCalled();
  });

  it("resend button calls resendVerification with the entered email and shows confirmation", async () => {
    const { ApiError } = await import("../services/api");
    mockedApi.login.mockRejectedValue(
      new ApiError(403, "Please verify your email before signing in."),
    );
    mockedApi.resendVerification.mockResolvedValue({ message: "ok" });

    renderLogin();
    await submitLoginForm("unverified@example.com");
    await screen.findByRole("button", { name: /resend verification email/i });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /resend verification email/i }));

    await waitFor(() => {
      expect(mockedApi.resendVerification).toHaveBeenCalledWith("unverified@example.com");
    });
    expect(await screen.findByText(/verification email sent/i)).toBeTruthy();
  });

  it("shows a plain invalid-credentials message for 401 without a resend button", async () => {
    const { ApiError } = await import("../services/api");
    mockedApi.login.mockRejectedValue(new ApiError(401, "Invalid credentials"));

    renderLogin();
    await submitLoginForm();

    expect(await screen.findByText("Invalid email or password.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /resend verification email/i })).toBeNull();
  });

  it("shows a disabled-account message for a 403 that doesn't mention verification", async () => {
    const { ApiError } = await import("../services/api");
    mockedApi.login.mockRejectedValue(new ApiError(403, "Account disabled"));

    renderLogin();
    await submitLoginForm();

    expect(await screen.findByText("Your account has been disabled.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /resend verification email/i })).toBeNull();
  });

  it("logs in and navigates normally when the account is verified", async () => {
    mockedApi.login.mockResolvedValue({
      access_token: "at",
      refresh_token: "rt",
      token_type: "bearer",
      expires_in: 1800,
      user: {
        id: "usr_1",
        email: "ada@example.com",
        username: null,
        display_name: "Ada",
        status: "active",
        email_verified: true,
      },
    } as Awaited<ReturnType<typeof api.login>>);
    mockedApi.getOrganizations.mockResolvedValue({ organizations: [] });

    renderLogin();
    await submitLoginForm();

    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBe("at");
    });
    expect(screen.queryByRole("button", { name: /resend verification email/i })).toBeNull();
  });

  it("navigates to a preserved ?redirect= target after login (EP-24.6)", async () => {
    mockedApi.login.mockResolvedValue({
      access_token: "at",
      refresh_token: "rt",
      token_type: "bearer",
      expires_in: 1800,
      user: {
        id: "usr_1",
        email: "ada@example.com",
        username: null,
        display_name: "Ada",
        status: "active",
        email_verified: true,
      },
    } as Awaited<ReturnType<typeof api.login>>);
    mockedApi.getOrganizations.mockResolvedValue({ organizations: [] });

    render(
      <MemoryRouter initialEntries={["/login?redirect=%2Faccept-invite%3Ftoken%3Dabc"]}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/accept-invite" element={<div>accept-invite landing</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await submitLoginForm();

    expect(await screen.findByText("accept-invite landing")).toBeTruthy();
  });
});
