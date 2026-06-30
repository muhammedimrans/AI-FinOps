// All monetary values arrive as strings (Decimal serialized from Python backend)

export type Currency = "USD" | "EUR" | "GBP";
export type Granularity = "daily" | "weekly" | "monthly";
export type Provider = "openai" | "anthropic" | "google" | "azure" | "bedrock" | "cohere";

export interface DateRange {
  start: string; // ISO date YYYY-MM-DD
  end: string;
}

export interface BaseParams {
  start_date: string;
  end_date: string;
  currency?: Currency;
}

// ── Overview ──────────────────────────────────────────────────────────────────

export interface OverviewKPIs {
  total_cost: string;
  total_requests: number;
  active_models: number;
  active_providers: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_cost_per_request: string;
  cost_trend_pct: number;
  request_trend_pct: number;
  token_trend_pct: number;
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
  budget: string;
  budget_utilization_pct: number;
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

// ── Filter state ──────────────────────────────────────────────────────────────

export interface FilterState {
  dateRange: DateRange;
  currency: Currency;
  granularity: Granularity;
  providers: string[];
  models: string[];
  projects: string[];
}
