import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// features/Overview.tsx transitively imports the theme store (via
// lib/chartPalette), which reads window.matchMedia on first access —
// jsdom doesn't implement it, so stub it before that import runs.
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

const { DashboardStateHero } = await import("../features/Overview");

// EP-22.3 — the dashboard state machine's 4 states (§ Dashboard State
// Machine): 1 = no providers, 2 = provider unvalidated, 3 = validated but
// no usage, 4 = usage exists (hero renders nothing, full dashboard shows).

function renderHero(state: 1 | 2 | 3 | 4) {
  return render(
    <MemoryRouter>
      <DashboardStateHero state={state} />
    </MemoryRouter>,
  );
}

describe("DashboardStateHero", () => {
  it("state 1 — shows the welcome message with a Connect Provider CTA", () => {
    renderHero(1);
    expect(screen.getByText("Welcome to Costorah")).toBeTruthy();
    expect(
      screen.getByText(/one step away from tracking AI costs/i),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Connect Provider" })).toHaveProperty(
      "href",
      expect.stringContaining("/connections"),
    );
    expect(screen.getByRole("link", { name: "Learn More" })).toBeTruthy();
  });

  it("state 2 — shows the validate-credentials message with a Validate Connection CTA", () => {
    renderHero(2);
    expect(screen.getByText("Provider connected")).toBeTruthy();
    expect(screen.getByText(/Validate your API credentials/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Validate Connection" })).toHaveProperty(
      "href",
      expect.stringContaining("/connections"),
    );
  });

  it("state 3 — shows the waiting-for-requests message with a View Providers CTA", () => {
    renderHero(3);
    expect(screen.getByText("Everything is ready.")).toBeTruthy();
    expect(screen.getByText(/Waiting for your applications/i)).toBeTruthy();
    expect(screen.getByText("Token usage")).toBeTruthy();
    expect(screen.getByText("Spending")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View Providers" })).toBeTruthy();
  });

  it("state 4 — renders nothing, letting the full dashboard show", () => {
    const { container } = renderHero(4);
    expect(container.textContent).toBe("");
  });
});
