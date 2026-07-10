// All monetary values arrive as strings (Decimal serialized from Python backend)

export type Currency = "USD" | "EUR" | "GBP";
export type Granularity = "daily" | "weekly" | "monthly";
export type Provider = "openai" | "anthropic" | "google" | "azure" | "bedrock" | "cohere";

// ── Overview ──────────────────────────────────────────────────────────────────

export interface OverviewKPIs {
  total_cost: string;
  today_cost: string;
  month_cost: string;
  total_requests: number;
  active_models: number;
  active_providers: number;
  active_projects: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_cost_per_request: string;
  cost_trend_pct: number | null;
  request_trend_pct: number | null;
  token_trend_pct: number | null;
  currency: Currency;
  period_start: string;
  period_end: string;
}

// ── Time Series ───────────────────────────────────────────────────────────────

export interface TimeSeriesPoint {
  date: string;
  total_cost: string;
  total_requests: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  provider_breakdown: Record<string, string>;
}

export interface TimeSeriesResponse {
  data: TimeSeriesPoint[];
  granularity: Granularity;
  currency: Currency;
}

// ── Providers ─────────────────────────────────────────────────────────────────

export interface ProviderSummary {
  provider: string;
  total_cost: string;
  request_count: number;
  model_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_share_pct: number;
}

export interface ProvidersResponse {
  providers: ProviderSummary[];
  currency: Currency;
}

// ── Models ────────────────────────────────────────────────────────────────────

export interface ModelSummary {
  model_id: string;
  provider: string;
  display_name: string;
  total_cost: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  avg_cost_per_request: string;
  cost_per_1k_tokens: string;
}

export interface ModelsResponse {
  models: ModelSummary[];
  currency: Currency;
}

// ── Projects ──────────────────────────────────────────────────────────────────

export interface ProjectCost {
  project_id: string;
  project_name: string;
  team: string;
  total_cost: string;
  budget: string | null;
  budget_utilization_pct: number | null;
  request_count: number;
  top_models: string[];
  cost_trend: number;
  trend_data: string[];
}

export interface ProjectsResponse {
  projects: ProjectCost[];
  currency: Currency;
}

// ── Organization ──────────────────────────────────────────────────────────────

export interface DepartmentCost {
  department_id: string;
  department_name: string;
  total_cost: string;
  budget: string;
  budget_utilization_pct: number;
  team_count: number;
  project_count: number;
  request_count: number;
}

export interface OrganizationResponse {
  departments: DepartmentCost[];
  total_cost: string;
  total_budget: string;
  currency: Currency;
}

// ── KPIs ──────────────────────────────────────────────────────────────────────

export interface KPIItem {
  key: string;
  label: string;
  value: string;
  unit: string;
  trend_pct: number;
  trend_direction: "up" | "down" | "flat";
}

export interface KPIsResponse {
  kpis: KPIItem[];
  currency: Currency;
  as_of: string;
}

// ── Usage Events (recent activity) ───────────────────────────────────────────

export interface UsageEvent {
  id: string;
  timestamp: string;
  provider: string;
  model_id: string;
  organization_name: string;
  project_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: string;
  currency: Currency;
}

export interface UsageEventsResponse {
  events: UsageEvent[];
  total: number;
  page: number;
  page_size: number;
}

// ── Usage Heatmap (EP-24.1) ──────────────────────────────────────────────────

export interface HeatmapCell {
  hour_of_day: number; // 0-23 (UTC)
  day_of_week: number; // 0=Sunday .. 6=Saturday
  total_cost: string;
  total_tokens: number;
  total_requests: number;
}

export interface HeatmapResponse {
  cells: HeatmapCell[];
  currency: Currency;
}

// ── Recent Activity (EP-24.1) ────────────────────────────────────────────────

export interface ActivityRunItem {
  id: string;
  provider: string;
  status: string;
  triggeredBy: string;
  startedAt: string;
  completedAt: string | null;
  eventsCollected: number;
  errorMessage: string | null;
}

export interface ActivityFailureItem {
  connectionId: string;
  providerType: string;
  displayName: string;
  lastError: string | null;
  lastFailureAt: string | null;
  consecutiveFailureCount: number;
}

export interface ActivityFeed {
  imports: ActivityRunItem[];
  syncs: ActivityRunItem[];
  failures: ActivityFailureItem[];
}
