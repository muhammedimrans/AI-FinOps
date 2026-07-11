import { describe, it, expect } from "vitest";
import {
  estimateCostForModel,
  formatCost,
  formatExecutionTime,
  formatLatency,
  formatRelativeDay,
  groupByRelativeDay,
} from "../features/playground/format";
import type { PlaygroundExecutionRecord } from "../services/api";

function execution(overrides: Partial<PlaygroundExecutionRecord> = {}): PlaygroundExecutionRecord {
  return {
    id: "pgexec_1",
    provider: "openai",
    model: "gpt-4o",
    provider_connection_id: "conn_1",
    project_id: null,
    system_prompt: null,
    user_prompt: "hi",
    response_text: "hello",
    temperature: 0.7,
    top_p: 1,
    max_tokens: 100,
    prompt_tokens: 1000,
    completion_tokens: 500,
    total_tokens: 1500,
    estimated_cost: "0.01",
    currency: "USD",
    latency_ms: 1234,
    status: "succeeded",
    error_message: null,
    comparison_group_id: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("playground/format", () => {
  it("formatCost renders '<$0.01' for sub-cent amounts", () => {
    expect(formatCost("0.0003", "USD")).toBe("<$0.01 USD");
  });

  it("formatCost renders a real dollar figure above one cent", () => {
    expect(formatCost("0.0123", "USD")).toBe("$0.0123 USD");
  });

  it("formatCost returns an em dash for null (no pricing configured)", () => {
    expect(formatCost(null, "USD")).toBe("—");
  });

  it("formatLatency/formatExecutionTime derive from the same latency_ms", () => {
    expect(formatLatency(1234)).toBe("1234ms");
    expect(formatExecutionTime(1234)).toBe("1.23s");
    expect(formatLatency(null)).toBe("—");
    expect(formatExecutionTime(null)).toBe("—");
  });

  it("formatRelativeDay classifies today/yesterday/earlier correctly", () => {
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const lastWeek = new Date(now);
    lastWeek.setDate(now.getDate() - 8);

    expect(formatRelativeDay(now.toISOString())).toBe("Today");
    expect(formatRelativeDay(yesterday.toISOString())).toBe("Yesterday");
    expect(formatRelativeDay(lastWeek.toISOString())).toBe("Earlier");
  });

  it("groupByRelativeDay groups and orders Today/Yesterday/Earlier, dropping empty groups", () => {
    const now = new Date();
    const lastWeek = new Date(now);
    lastWeek.setDate(now.getDate() - 8);

    const items = [
      execution({ id: "a", created_at: now.toISOString() }),
      execution({ id: "b", created_at: lastWeek.toISOString() }),
    ];
    const groups = groupByRelativeDay(items);
    expect(groups.map((g) => g.label)).toEqual(["Today", "Earlier"]);
    expect(groups[0]!.items.map((i) => i.id)).toEqual(["a"]);
    expect(groups[1]!.items.map((i) => i.id)).toEqual(["b"]);
  });

  it("estimateCostForModel computes real cost from real token counts and rates", () => {
    const exec = execution({ prompt_tokens: 1000, completion_tokens: 500 });
    // 1000/1000 * 0.005 + 500/1000 * 0.015 = 0.005 + 0.0075 = 0.0125
    expect(estimateCostForModel(exec, 0.005, 0.015)).toBeCloseTo(0.0125, 6);
  });
});
