import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import AlertTimeline from "../components/AlertTimeline";
import type { AlertRecord } from "../services/api";

function baseAlert(overrides: Partial<AlertRecord> = {}): AlertRecord {
  return {
    id: "alert_1",
    alert_type: "budget_exceeded",
    severity: "critical",
    status: "open",
    title: "Prod: budget exceeded",
    message: "Prod has used 110% of its budget this month.",
    source: "ingestion",
    occurrence_count: 1,
    metadata: {},
    first_occurred_at: "2026-07-01T10:00:00Z",
    last_occurred_at: "2026-07-01T10:00:00Z",
    acknowledged_by: null,
    acknowledged_at: null,
    acknowledgement_reason: null,
    resolved_at: null,
    dismissed_at: null,
    created_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

describe("AlertTimeline", () => {
  it("always shows a Created step", () => {
    render(<AlertTimeline alert={baseAlert()} />);
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.queryByText("Acknowledged")).not.toBeInTheDocument();
    expect(screen.queryByText("Resolved")).not.toBeInTheDocument();
    expect(screen.queryByText("Dismissed")).not.toBeInTheDocument();
  });

  it("shows Acknowledged with its reason once acknowledged", () => {
    render(
      <AlertTimeline
        alert={baseAlert({
          status: "acknowledged",
          acknowledged_at: "2026-07-01T11:00:00Z",
          acknowledgement_reason: "Investigating with the team",
        })}
      />,
    );
    expect(screen.getByText("Acknowledged")).toBeInTheDocument();
    expect(screen.getByText("Investigating with the team")).toBeInTheDocument();
  });

  it("shows Resolved once resolved", () => {
    render(
      <AlertTimeline
        alert={baseAlert({ status: "resolved", resolved_at: "2026-07-01T12:00:00Z" })}
      />,
    );
    expect(screen.getByText("Resolved")).toBeInTheDocument();
  });

  it("shows Dismissed once dismissed", () => {
    render(
      <AlertTimeline
        alert={baseAlert({ status: "dismissed", dismissed_at: "2026-07-01T12:30:00Z" })}
      />,
    );
    expect(screen.getByText("Dismissed")).toBeInTheDocument();
  });

  it("orders steps chronologically regardless of field declaration order", () => {
    render(
      <AlertTimeline
        alert={baseAlert({
          status: "resolved",
          acknowledged_at: "2026-07-01T11:00:00Z",
          resolved_at: "2026-07-01T12:00:00Z",
        })}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Created");
    expect(items[1]).toHaveTextContent("Acknowledged");
    expect(items[2]).toHaveTextContent("Resolved");
  });
});
