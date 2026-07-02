import { describe, it, expect } from "vitest";
import { linearForecast, detectAnomalies, type SeriesPoint } from "../lib/insights";

function series(values: number[], startDate = "2026-06-01"): SeriesPoint[] {
  const start = new Date(`${startDate}T00:00:00Z`);
  return values.map((value, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i);
    return { date: d.toISOString().slice(0, 10), value };
  });
}

describe("linearForecast", () => {
  it("returns null for series shorter than 7 points", () => {
    expect(linearForecast(series([1, 2, 3]), 7)).toBeNull();
  });

  it("returns null for a non-positive horizon", () => {
    expect(linearForecast(series([1, 2, 3, 4, 5, 6, 7]), 0)).toBeNull();
  });

  it("projects a perfect linear trend exactly", () => {
    const result = linearForecast(series([10, 20, 30, 40, 50, 60, 70]), 3);
    expect(result).not.toBeNull();
    expect(result!.dailySlope).toBeCloseTo(10);
    expect(result!.points.map((p) => p.value)).toEqual([80, 90, 100]);
  });

  it("projects a flat series as flat", () => {
    const result = linearForecast(series(Array.from({ length: 10 }, () => 42)), 5);
    expect(result!.dailySlope).toBeCloseTo(0);
    for (const p of result!.points) expect(p.value).toBeCloseTo(42);
  });

  it("clamps projections at zero for steep downtrends", () => {
    const result = linearForecast(series([70, 60, 50, 40, 30, 20, 10]), 5);
    expect(result!.points.every((p) => p.value >= 0)).toBe(true);
    expect(result!.points.at(-1)!.value).toBe(0);
  });

  it("continues dates daily after the last observation", () => {
    const result = linearForecast(series([1, 2, 3, 4, 5, 6, 7], "2026-06-01"), 2);
    expect(result!.points[0]!.date).toBe("2026-06-08");
    expect(result!.points[1]!.date).toBe("2026-06-09");
  });

  it("sums the projected total across the horizon", () => {
    const result = linearForecast(series([10, 20, 30, 40, 50, 60, 70]), 3);
    expect(result!.projectedTotal).toBeCloseTo(80 + 90 + 100);
  });
});

describe("detectAnomalies", () => {
  it("flags nothing on a stable series", () => {
    expect(detectAnomalies(series([5, 5, 5, 5, 5, 5, 5, 5, 5, 5]))).toEqual([]);
  });

  it("flags a spike beyond the sigma threshold", () => {
    const values = [10, 11, 9, 10, 11, 9, 10, 50];
    const anomalies = detectAnomalies(series(values), { window: 7, threshold: 2 });
    expect(anomalies).toHaveLength(1);
    expect(anomalies[0]!.value).toBe(50);
    expect(anomalies[0]!.sigma).toBeGreaterThan(2);
  });

  it("flags a drop with negative sigma", () => {
    const values = [100, 102, 98, 101, 99, 100, 101, 20];
    const anomalies = detectAnomalies(series(values), { window: 7, threshold: 2 });
    expect(anomalies).toHaveLength(1);
    expect(anomalies[0]!.sigma).toBeLessThan(-2);
  });

  it("never flags points inside the initial window", () => {
    const values = [1000, 1, 1, 1, 1, 1, 1];
    const anomalies = detectAnomalies(series(values), { window: 7 });
    expect(anomalies).toEqual([]);
  });

  it("flags any change from a zero-variance window", () => {
    const values = [5, 5, 5, 5, 5, 5, 5, 6];
    const anomalies = detectAnomalies(series(values), { window: 7 });
    expect(anomalies).toHaveLength(1);
    expect(anomalies[0]!.sigma).toBe(Infinity);
  });

  it("respects a custom threshold", () => {
    const values = [10, 11, 9, 10, 11, 9, 10, 13];
    const loose = detectAnomalies(series(values), { window: 7, threshold: 5 });
    const strict = detectAnomalies(series(values), { window: 7, threshold: 1 });
    expect(loose).toHaveLength(0);
    expect(strict.length).toBeGreaterThan(0);
  });
});
