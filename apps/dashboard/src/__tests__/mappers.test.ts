import { describe, it, expect } from "vitest";
import {
  mapOverview,
  mapTimeSeries,
  mapProviders,
  mapModels,
  mapProjects,
  mapHeatmap,
  mapActivity,
} from "../lib/mappers";
import type {
  BackendOverviewResponse,
  BackendTimeSeriesResponse,
  BackendProviderBreakdownResponse,
  BackendModelBreakdownResponse,
  BackendProjectBreakdownResponse,
  BackendHeatmapResponse,
  BackendActivityResponse,
} from "../types/backend";

// EP-24.1 — these tests pin the "gap" fields in lib/mappers.ts that this EP
// closed (they used to be hardcoded zeros/placeholders regardless of what
// the backend sent). Each assertion below would fail against the pre-EP-24.1
// mapper, since the field either didn't exist on the request or was always 0.

describe("mapOverview (EP-24.1)", () => {
  const backend: BackendOverviewResponse = {
    total_spend: "123.45",
    today_spend: "5.00",
    month_spend: "80.00",
    total_tokens: 10000,
    total_requests: 50,
    active_providers: 3,
    active_models: 7,
    active_projects: 4,
    avg_cost_per_request: "2.469",
    cost_trend_pct: "12.5",
    request_trend_pct: "-3.2",
    token_trend_pct: null,
    collection_status: "completed",
    last_collection_at: "2026-07-10T00:00:00Z",
    currency: "USD",
  };

  it("surfaces active_projects, today/month spend, and avg_cost_per_request as real values", () => {
    const result = mapOverview(backend);
    expect(result.active_projects).toBe(4);
    expect(result.today_cost).toBe("5.00");
    expect(result.month_cost).toBe("80.00");
    expect(result.avg_cost_per_request).toBe("2.469");
  });

  it("surfaces real trend percentages instead of hardcoded 0", () => {
    const result = mapOverview(backend);
    expect(result.cost_trend_pct).toBe(12.5);
    expect(result.request_trend_pct).toBe(-3.2);
  });

  it("preserves null trend (no prior-period baseline) rather than coercing to 0", () => {
    const result = mapOverview(backend);
    expect(result.token_trend_pct).toBeNull();
  });
});

describe("mapTimeSeries (EP-24.1)", () => {
  it("carries prompt_tokens/completion_tokens through as input/output tokens", () => {
    const backend: BackendTimeSeriesResponse = {
      granularity: "daily",
      start_date: "2026-07-01",
      end_date: "2026-07-10",
      points: [
        {
          date: "2026-07-05",
          cost: "10.00",
          tokens: 1000,
          prompt_tokens: 700,
          completion_tokens: 300,
          requests: 5,
          currency: "USD",
        },
      ],
      total_cost: "10.00",
      total_tokens: 1000,
      total_requests: 5,
    };
    const result = mapTimeSeries(backend);
    expect(result.data[0]!.input_tokens).toBe(700);
    expect(result.data[0]!.output_tokens).toBe(300);
  });
});

describe("mapProviders (EP-24.1)", () => {
  it("surfaces model_count and real input/output token split", () => {
    const backend: BackendProviderBreakdownResponse = {
      providers: [
        {
          provider: "openai",
          total_cost: "50.00",
          total_tokens: 5000,
          input_tokens: 3500,
          output_tokens: 1500,
          model_count: 4,
          total_requests: 20,
          avg_cost_per_request: "2.5",
          currency: "USD",
        },
      ],
      total_cost: "50.00",
      period_start: "2026-07-01",
      period_end: "2026-07-10",
    };
    const result = mapProviders(backend);
    expect(result.providers[0]!.model_count).toBe(4);
    expect(result.providers[0]!.input_tokens).toBe(3500);
    expect(result.providers[0]!.output_tokens).toBe(1500);
  });
});

describe("mapModels (EP-24.1)", () => {
  it("surfaces real input/output token split instead of a total-as-proxy", () => {
    const backend: BackendModelBreakdownResponse = {
      models: [
        {
          provider: "openai",
          model: "gpt-4",
          total_cost: "30.00",
          total_tokens: 3000,
          input_tokens: 2000,
          output_tokens: 1000,
          total_requests: 10,
          avg_cost_per_request: "3.0",
          currency: "USD",
        },
      ],
      total_cost: "30.00",
      period_start: "2026-07-01",
      period_end: "2026-07-10",
    };
    const result = mapModels(backend);
    expect(result.models[0]!.input_tokens).toBe(2000);
    expect(result.models[0]!.output_tokens).toBe(1000);
  });
});

describe("mapProjects (EP-24.1)", () => {
  it("surfaces real project_name and budget instead of project_id/0", () => {
    const backend: BackendProjectBreakdownResponse = {
      projects: [
        {
          project_id: "proj_123",
          project_name: "Production API",
          total_cost: "40.00",
          total_tokens: 4000,
          total_requests: 12,
          budget: "100.00",
          budget_utilization_pct: "40.00",
          currency: "USD",
        },
      ],
      total_cost: "40.00",
      period_start: "2026-07-01",
      period_end: "2026-07-10",
    };
    const result = mapProjects(backend);
    expect(result.projects[0]!.project_name).toBe("Production API");
    expect(result.projects[0]!.budget).toBe("100.00");
    expect(result.projects[0]!.budget_utilization_pct).toBe(40);
  });

  it("preserves null budget (no budget set) rather than coercing to '0'", () => {
    const backend: BackendProjectBreakdownResponse = {
      projects: [
        {
          project_id: "proj_456",
          project_name: "No Budget Project",
          total_cost: "5.00",
          total_tokens: 500,
          total_requests: 2,
          budget: null,
          budget_utilization_pct: null,
          currency: "USD",
        },
      ],
      total_cost: "5.00",
      period_start: "2026-07-01",
      period_end: "2026-07-10",
    };
    const result = mapProjects(backend);
    expect(result.projects[0]!.budget).toBeNull();
    expect(result.projects[0]!.budget_utilization_pct).toBeNull();
  });

  it("falls back to Unassigned for a null project_id", () => {
    const backend: BackendProjectBreakdownResponse = {
      projects: [
        {
          project_id: null,
          project_name: "Unassigned",
          total_cost: "1.00",
          total_tokens: 100,
          total_requests: 1,
          budget: null,
          budget_utilization_pct: null,
          currency: "USD",
        },
      ],
      total_cost: "1.00",
      period_start: "2026-07-01",
      period_end: "2026-07-10",
    };
    const result = mapProjects(backend);
    expect(result.projects[0]!.project_id).toBe("unattributed");
    expect(result.projects[0]!.project_name).toBe("Unassigned");
  });
});

describe("mapHeatmap (EP-24.1, new)", () => {
  it("maps every cell's hour/day/cost/tokens/requests through unchanged", () => {
    const backend: BackendHeatmapResponse = {
      cells: [
        {
          hour_of_day: 14,
          day_of_week: 2,
          total_cost: "3.50",
          total_tokens: 350,
          total_requests: 7,
          currency: "USD",
        },
      ],
      period_start: "2026-07-01",
      period_end: "2026-07-10",
      currency: "USD",
    };
    const result = mapHeatmap(backend);
    expect(result.cells).toHaveLength(1);
    expect(result.cells[0]).toEqual({
      hour_of_day: 14,
      day_of_week: 2,
      total_cost: "3.50",
      total_tokens: 350,
      total_requests: 7,
    });
  });

  it("maps an empty grid to an empty cells array", () => {
    const backend: BackendHeatmapResponse = {
      cells: [],
      period_start: "2026-07-01",
      period_end: "2026-07-10",
      currency: "USD",
    };
    expect(mapHeatmap(backend).cells).toEqual([]);
  });
});

describe("mapActivity (EP-24.1, new)", () => {
  it("splits imports/syncs and converts failure fields to camelCase", () => {
    const backend: BackendActivityResponse = {
      imports: [
        {
          id: "run_1",
          provider: "openai",
          status: "completed",
          triggered_by: "manual",
          started_at: "2026-07-10T10:00:00Z",
          completed_at: "2026-07-10T10:01:00Z",
          events_collected: 42,
          error_message: null,
        },
      ],
      syncs: [
        {
          id: "run_2",
          provider: "anthropic",
          status: "failed",
          triggered_by: "scheduled",
          started_at: "2026-07-10T09:00:00Z",
          completed_at: null,
          events_collected: 0,
          error_message: "timeout",
        },
      ],
      failures: [
        {
          connection_id: "conn_1",
          provider_type: "openai",
          display_name: "Prod OpenAI",
          last_error: "The API key is invalid or has been revoked.",
          last_failure_at: "2026-07-10T08:00:00Z",
          consecutive_failure_count: 3,
        },
      ],
    };
    const result = mapActivity(backend);
    expect(result.imports).toHaveLength(1);
    expect(result.imports[0]!.eventsCollected).toBe(42);
    expect(result.syncs).toHaveLength(1);
    expect(result.syncs[0]!.errorMessage).toBe("timeout");
    expect(result.failures).toHaveLength(1);
    expect(result.failures[0]!.displayName).toBe("Prod OpenAI");
    expect(result.failures[0]!.consecutiveFailureCount).toBe(3);
  });

  it("maps an all-empty feed to empty arrays", () => {
    const backend: BackendActivityResponse = { imports: [], syncs: [], failures: [] };
    const result = mapActivity(backend);
    expect(result).toEqual({ imports: [], syncs: [], failures: [] });
  });
});
