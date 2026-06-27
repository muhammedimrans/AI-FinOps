/** Overall health status. */
export type HealthStatus = "healthy" | "degraded" | "unhealthy";

/** Individual dependency check result. */
export interface DependencyHealth {
  readonly name: string;
  readonly status: HealthStatus;
  readonly latencyMs: number | null;
  readonly message?: string;
}

/** GET /health response. */
export interface HealthResponse {
  readonly status: HealthStatus;
  readonly version: string;
  readonly uptime: number;
  readonly timestamp: string;
  readonly dependencies: readonly DependencyHealth[];
}

/** GET /ready response. */
export interface ReadyResponse {
  readonly ready: boolean;
  readonly checks: ReadonlyArray<{
    readonly name: string;
    readonly passed: boolean;
    readonly message?: string;
  }>;
}

/** GET /metrics response (placeholder — real metrics served in Prometheus format). */
export interface MetricsResponse {
  readonly format: "prometheus";
  readonly contentType: "text/plain; version=0.0.4; charset=utf-8";
}
