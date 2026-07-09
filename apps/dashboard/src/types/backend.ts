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
  collection_status: string | null;
  last_collection_at: string | null;
  currency: BackendCurrency;
}

// ── F-061 Time Series ─────────────────────────────────────────────────────────

export interface BackendTimeSeriesPoint {
  date: string;
  cost: string;
  tokens: number;
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
// NOTE: no project_name, budget, team, top_models, or trend data

export interface BackendProjectMetrics {
  project_id: string | null;
  total_cost: string;
  total_tokens: number;
  total_requests: number;
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
