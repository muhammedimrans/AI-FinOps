// Exact TypeScript mirrors of the backend Pydantic schemas.
// These are the shapes that the live API actually returns.
// Use mappers in lib/mappers.ts to convert to the frontend component types (types/api.ts).

export type BackendCurrency = string; // backend sends any ISO 4217 code as plain string

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface BackendUserPublic {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  status: string;
  email_verified: boolean;
  // EP-21.3: true once the first-time onboarding wizard (/onboarding) has
  // been completed. The backend always sends this — it's the frontend's
  // own *persisted* AuthUser (see stores/auth.ts) that can predate the
  // field and needs the optional/undefined handling, not this wire type.
  onboarding_completed: boolean;
  // EP-22.2 Settings — profile fields + the free-form preferences bag.
  avatar_url: string | null;
  bio: string | null;
  timezone: string | null;
  created_at: string;
  preferences: Record<string, unknown>;
}

export interface BackendLoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: BackendUserPublic;
}

export interface BackendTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface BackendMessageResponse {
  message: string;
}

// ── F-060 Overview ────────────────────────────────────────────────────────────

export interface BackendOverviewResponse {
  total_spend: string;
  today_spend: string;
  month_spend: string;
  total_tokens: number;
  total_requests: number;
  active_providers: number;
  active_models: number;
  // EP-24.1
  active_projects: number;
  avg_cost_per_request: string;
  cost_trend_pct: string | null;
  request_trend_pct: string | null;
  token_trend_pct: string | null;
  collection_status: string | null;
  last_collection_at: string | null;
  currency: BackendCurrency;
}

// ── F-061 Time Series ─────────────────────────────────────────────────────────

export interface BackendTimeSeriesPoint {
  date: string;
  cost: string;
  tokens: number;
  prompt_tokens: number; // EP-24.1
  completion_tokens: number; // EP-24.1
  requests: number;
  currency: BackendCurrency;
}

export interface BackendTimeSeriesResponse {
  granularity: string;
  start_date: string;
  end_date: string;
  points: BackendTimeSeriesPoint[];
  total_cost: string;
  total_tokens: number;
  total_requests: number;
}

// ── F-062 Provider Breakdown ──────────────────────────────────────────────────

export interface BackendProviderMetrics {
  provider: string;
  total_cost: string;
  total_tokens: number;
  input_tokens: number; // EP-24.1
  output_tokens: number; // EP-24.1
  model_count: number; // EP-24.1
  total_requests: number;
  avg_cost_per_request: string;
  currency: BackendCurrency;
}

export interface BackendProviderBreakdownResponse {
  providers: BackendProviderMetrics[];
  total_cost: string;
  period_start: string;
  period_end: string;
}

// ── F-063 Model Breakdown ─────────────────────────────────────────────────────
// NOTE: backend field is `model`, not `model_id`

export interface BackendModelMetrics {
  provider: string;
  model: string;
  total_cost: string;
  total_tokens: number;
  input_tokens: number; // EP-24.1
  output_tokens: number; // EP-24.1
  total_requests: number;
  avg_cost_per_request: string;
  currency: BackendCurrency;
}

export interface BackendModelBreakdownResponse {
  models: BackendModelMetrics[];
  total_cost: string;
  period_start: string;
  period_end: string;
}

// ── F-064 Organization Dashboard (composite) ──────────────────────────────────

export interface BackendOrganizationOverviewBlock {
  total_spend: string;
  today_spend: string;
  month_spend: string;
  total_tokens: number;
  total_requests: number;
  active_providers: number;
  active_models: number;
  collection_status: string | null;
  last_collection_at: string | null;
}

export interface BackendOrganizationProviderItem {
  provider: string;
  total_cost: string;
  total_tokens: number;
  total_requests: number;
  avg_cost_per_request: string;
  currency: BackendCurrency;
}

export interface BackendOrganizationModelItem {
  provider: string;
  model: string;
  total_cost: string;
  total_tokens: number;
  total_requests: number;
  avg_cost_per_request: string;
  currency: BackendCurrency;
}

export interface BackendOrganizationProjectItem {
  project_id: string | null;
  total_cost: string;
  total_tokens: number;
  total_requests: number;
  currency: BackendCurrency;
}

export interface BackendOrganizationTrendPoint {
  date: string;
  cost: string;
  tokens: number;
  requests: number;
  currency: BackendCurrency;
}

export interface BackendOrganizationDashboardResponse {
  organization_id: string;
  period_start: string;
  period_end: string;
  currency: BackendCurrency;
  overview: BackendOrganizationOverviewBlock;
  provider_breakdown: BackendOrganizationProviderItem[];
  top_models: BackendOrganizationModelItem[];
  project_breakdown: BackendOrganizationProjectItem[];
  daily_trend: BackendOrganizationTrendPoint[];
}

// ── F-065 Project Breakdown ───────────────────────────────────────────────────
// EP-24.1: project_name and budget are now real; no team/top_models/trend data yet

export interface BackendProjectMetrics {
  project_id: string | null;
  project_name: string; // EP-24.1
  total_cost: string;
  total_tokens: number;
  total_requests: number;
  budget: string | null; // EP-24.1
  budget_utilization_pct: string | null; // EP-24.1
  currency: BackendCurrency;
}

export interface BackendProjectBreakdownResponse {
  projects: BackendProjectMetrics[];
  total_cost: string;
  period_start: string;
  period_end: string;
}

// ── EP-12.1 Organizations ─────────────────────────────────────────────────────

export interface BackendOrgMembershipItem {
  id: string;   // org external_id e.g. "org_<hex>"
  name: string;
  slug: string;
  role: string; // "owner" | "admin" | "member" | "viewer"
  // EP-22.2 Settings — Workspace section fields.
  description?: string | null;
  is_personal?: boolean;
  created_at?: string | null;
}

export interface BackendOrganizationsResponse {
  organizations: BackendOrgMembershipItem[];
}

// ── F-066 KPIs ────────────────────────────────────────────────────────────────
// NOTE: named fields, not a generic KPIItem array like the frontend type

export interface BackendKPIResponse {
  highest_cost_provider: string | null;
  highest_cost_model: string | null;
  avg_cost_per_request: string | null;
  avg_cost_per_token: string | null;
  period_start: string;
  period_end: string;
  currency: BackendCurrency;
}

// ── EP-24.1 Usage Heatmap ──────────────────────────────────────────────────────

export interface BackendHeatmapCell {
  hour_of_day: number; // 0-23 (UTC)
  day_of_week: number; // 0=Sunday .. 6=Saturday
  total_cost: string;
  total_tokens: number;
  total_requests: number;
  currency: BackendCurrency;
}

export interface BackendHeatmapResponse {
  cells: BackendHeatmapCell[];
  period_start: string;
  period_end: string;
  currency: BackendCurrency;
}

// ── EP-24.1 Recent Activity ─────────────────────────────────────────────────────

export interface BackendActivityRunItem {
  id: string;
  provider: string;
  status: string;
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
  events_collected: number;
  error_message: string | null;
}

export interface BackendActivityFailureItem {
  connection_id: string;
  provider_type: string;
  display_name: string;
  last_error: string | null;
  last_failure_at: string | null;
  consecutive_failure_count: number;
}

export interface BackendActivityResponse {
  imports: BackendActivityRunItem[];
  syncs: BackendActivityRunItem[];
  failures: BackendActivityFailureItem[];
}
