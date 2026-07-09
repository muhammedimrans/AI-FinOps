// Client-side spend intelligence — computed from the real time series the
// dashboard already fetches. These are transparent statistical helpers, not
// server-side ML: every consumer must label output as an in-app projection.

export interface SeriesPoint {
  date: string; // ISO date
  value: number;
}

export interface ForecastPoint {
  date: string;
  value: number;
}

export interface ForecastResult {
  points: ForecastPoint[];
  /** Average change per day of the fitted trend (currency units/day). */
  dailySlope: number;
  /** Sum of projected values across the horizon. */
  projectedTotal: number;
}

/**
 * Least-squares linear fit over the series, projected `horizonDays` past the
 * last observation. Returns null when the series is too short to fit a
 * meaningful trend (< 7 points) — callers should hide the forecast entirely
 * rather than show a projection built on noise.
 */
export function linearForecast(series: SeriesPoint[], horizonDays: number): ForecastResult | null {
  if (series.length < 7 || horizonDays < 1) return null;

  const n = series.length;
  const xs = series.map((_, i) => i);
  const ys = series.map((p) => p.value);
  const xMean = xs.reduce((a, b) => a + b, 0) / n;
  const yMean = ys.reduce((a, b) => a + b, 0) / n;

  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i]! - xMean) * (ys[i]! - yMean);
    den += (xs[i]! - xMean) ** 2;
  }
  const slope = den === 0 ? 0 : num / den;
  const intercept = yMean - slope * xMean;

  const lastDate = new Date(`${series[n - 1]!.date}T00:00:00Z`);
  const points: ForecastPoint[] = [];
  let projectedTotal = 0;
  for (let d = 1; d <= horizonDays; d++) {
    const value = Math.max(0, intercept + slope * (n - 1 + d));
    const date = new Date(lastDate);
    date.setUTCDate(date.getUTCDate() + d);
    points.push({ date: date.toISOString().slice(0, 10), value });
    projectedTotal += value;
  }

  return { points, dailySlope: slope, projectedTotal };
}

export interface Anomaly {
  index: number;
  date: string;
  value: number;
  /** Trailing-window mean the value deviated from. */
  expected: number;
  /** Signed deviation in standard deviations. */
  sigma: number;
}

/**
 * Rolling-window anomaly detection: a point is anomalous when it deviates
 * from the mean of the preceding `window` points by more than `threshold`
 * standard deviations. Requires a full trailing window, so the first
 * `window` points are never flagged. Zero-variance windows flag any change.
 */
export function detectAnomalies(
  series: SeriesPoint[],
  { window = 7, threshold = 2 }: { window?: number; threshold?: number } = {},
): Anomaly[] {
  const anomalies: Anomaly[] = [];
  for (let i = window; i < series.length; i++) {
    const trailing = series.slice(i - window, i).map((p) => p.value);
    const mean = trailing.reduce((a, b) => a + b, 0) / window;
    const variance = trailing.reduce((a, b) => a + (b - mean) ** 2, 0) / window;
    const std = Math.sqrt(variance);
    const current = series[i]!;

    if (std === 0) {
      if (current.value !== mean) {
        anomalies.push({
          index: i,
          date: current.date,
          value: current.value,
          expected: mean,
          sigma: current.value > mean ? Infinity : -Infinity,
        });
      }
      continue;
    }

    const sigma = (current.value - mean) / std;
    if (Math.abs(sigma) > threshold) {
      anomalies.push({ index: i, date: current.date, value: current.value, expected: mean, sigma });
    }
  }
  return anomalies;
}
