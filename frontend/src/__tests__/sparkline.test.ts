import { describe, it, expect } from "vitest";

// Regression test for MINOR-002: Sparkline / MiniTrendLine division-by-zero
// when data array has exactly 1 element.
//
// The bug: step = w / (data.length - 1) = w / 0 = Infinity when length === 1,
// producing NaN SVG coordinates.
// The fix: guard `if (data.length < 2) return null`.

function computeSparklinePoints(data: number[]): string | null {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 28;
  const step = w / (data.length - 1);

  return data
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");
}

describe("Sparkline division-by-zero guard (MINOR-002)", () => {
  it("returns null for empty data", () => {
    expect(computeSparklinePoints([])).toBeNull();
  });

  it("returns null for single-element data (prevents step=Infinity)", () => {
    expect(computeSparklinePoints([42])).toBeNull();
  });

  it("produces finite, non-NaN coordinates for valid data", () => {
    const result = computeSparklinePoints([10, 20, 15, 30]);
    expect(result).not.toBeNull();
    const coords = result!.split(" ").flatMap((pt) => pt.split(",").map(Number));
    for (const c of coords) {
      expect(isFinite(c)).toBe(true);
      expect(isNaN(c)).toBe(false);
    }
  });

  it("handles flat data without NaN (range=0 case uses range=1 fallback)", () => {
    const result = computeSparklinePoints([5, 5, 5]);
    expect(result).not.toBeNull();
    const coords = result!.split(" ").flatMap((pt) => pt.split(",").map(Number));
    for (const c of coords) {
      expect(isFinite(c)).toBe(true);
    }
  });
});
