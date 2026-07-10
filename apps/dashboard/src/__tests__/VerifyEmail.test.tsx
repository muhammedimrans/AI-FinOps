import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../services/api";

// features/VerifyEmail.tsx renders AuthShell -> ThemeSwitcher, which reads
// the theme store, which reads window.matchMedia on first access — jsdom
// doesn't implement it (same pattern as Settings.test.tsx).
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

const { default: VerifyEmail } = await import("../features/VerifyEmail");

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    verifyEmail: vi.fn(),
    resendVerification: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("VerifyEmail — EP-24.4", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows an invalid-link message when there's no token", () => {
    renderAt("/verify-email");
    expect(screen.getByText(/invalid verification link/i)).toBeTruthy();
  });

  it("shows a success state once verifyEmail resolves", async () => {
    mockedApi.verifyEmail.mockResolvedValue({ message: "Email verified successfully" });
    renderAt("/verify-email?token=raw-token");

    await waitFor(() => {
      expect(screen.getByText("Email verified")).toBeTruthy();
    });
    expect(mockedApi.verifyEmail).toHaveBeenCalledWith("raw-token");
  });

  it("shows an error state with a resend form when the token is invalid", async () => {
    const { ApiError } = await import("../services/api");
    mockedApi.verifyEmail.mockRejectedValue(new ApiError(400, "bad token"));
    renderAt("/verify-email?token=bad-token");

    await waitFor(() => {
      expect(screen.getByText("Verification failed")).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: /resend verification email/i })).toBeTruthy();
  });

  it("resend form submits the entered email and shows a confirmation", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("../services/api");
    mockedApi.verifyEmail.mockRejectedValue(new ApiError(400, "bad token"));
    mockedApi.resendVerification.mockResolvedValue({ message: "ok" });
    renderAt("/verify-email?token=bad-token");

    await waitFor(() => {
      expect(screen.getByText("Verification failed")).toBeTruthy();
    });

    await user.type(screen.getByLabelText(/get a new verification link/i), "a@example.com");
    await user.click(screen.getByRole("button", { name: /resend verification email/i }));

    await waitFor(() => {
      expect(mockedApi.resendVerification).toHaveBeenCalledWith("a@example.com");
    });
    expect(await screen.findByText(/a new link is on its way/i)).toBeTruthy();
  });
});
