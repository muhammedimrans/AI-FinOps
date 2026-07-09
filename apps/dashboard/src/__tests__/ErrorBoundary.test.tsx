import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import ErrorBoundary from "../components/ErrorBoundary";

// Component that throws on demand
function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test explosion");
  return <div>Safe content</div>;
}

describe("ErrorBoundary (RH-05)", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Suppress React's error boundary console output in tests
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Safe content")).toBeTruthy();
  });

  it("renders fallback UI when a child throws", () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText(/Test explosion/)).toBeTruthy();
  });

  it("shows a Try again button in the fallback", () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
  });

  it("resets error state when Try again is clicked", () => {
    // Use a mutable flag so the child stops throwing before the reset re-renders it
    let shouldThrow = true;
    function DynamicBomb() {
      if (shouldThrow) throw new Error("Test explosion");
      return <div>Safe content</div>;
    }

    render(
      <ErrorBoundary>
        <DynamicBomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();

    const btn = screen.getByRole("button", { name: /try again/i });
    shouldThrow = false;
    act(() => {
      fireEvent.click(btn);
    });
    expect(screen.getByText("Safe content")).toBeTruthy();
  });

  it("renders custom fallback prop when provided", () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Custom fallback")).toBeTruthy();
  });
});
