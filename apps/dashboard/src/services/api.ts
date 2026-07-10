import type {
  OverviewKPIs,
  TimeSeriesResponse,
  ProvidersResponse,
  ModelsResponse,
  ProjectsResponse,
  OrganizationResponse,
  KPIsResponse,
  UsageEventsResponse,
  HeatmapResponse,
  ActivityFeed,
  Currency,
  Granularity,
} from "../types/api";
import type {
  BackendOverviewResponse,
  BackendTimeSeriesResponse,
  BackendProviderBreakdownResponse,
  BackendModelBreakdownResponse,
  BackendProjectBreakdownResponse,
  BackendOrganizationDashboardResponse,
  BackendKPIResponse,
  BackendHeatmapResponse,
  BackendActivityResponse,
  BackendLoginResponse,
  BackendTokenResponse,
  BackendOrganizationsResponse,
  BackendOrgMembershipItem,
  BackendUserPublic,
} from "../types/backend";
import {
  mapOverview,
  mapTimeSeries,
  mapProviders,
  mapModels,
  mapProjects,
  mapOrganization,
  mapKPIs,
  mapHeatmap,
  mapActivity,
} from "../lib/mappers";
import {
  getMockOverview,
  getMockTimeSeries,
  getMockProviders,
  getMockModels,
  getMockProjects,
  getMockOrganization,
  getMockKPIs,
  getMockRecentActivity,
  getMockHeatmap,
  getMockActivityFeed,
} from "../lib/mockData";
import { useAuthStore } from "../stores/auth";

// ── Configuration ─────────────────────────────────────────────────────────────

const BASE_URL: string =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

// Mock mode: explicit opt-in via VITE_ENABLE_MOCKS=true.
// In development, set VITE_ENABLE_MOCKS=true in .env.development to use mock data.
// In production, this must be false (or absent) so real backend calls are made.
const USE_MOCK: boolean = import.meta.env["VITE_ENABLE_MOCKS"] === "true";

// ── Token management ──────────────────────────────────────────────────────────

function getAuthStore() {
  return useAuthStore.getState();
}

// Single in-flight refresh promise — prevents multiple concurrent refresh calls.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const { refreshToken, setAccessToken, clearAuth } = getAuthStore();
    if (!refreshToken) {
      clearAuth();
      throw new Error("No refresh token available");
    }
    const res = await fetch(`${BASE_URL}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      clearAuth();
      throw new Error(`Token refresh failed: ${res.status}`);
    }
    const data = (await res.json()) as BackendTokenResponse;
    setAccessToken(data.access_token);
    // Update persisted refresh token with the rotated one
    getAuthStore().setLogin(data.access_token, data.refresh_token, getAuthStore().user!);
    return data.access_token;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

// ── Core HTTP client ──────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  options: {
    params?: Record<string, string | undefined>;
    body?: unknown;
    skipAuth?: boolean;
  } = {},
): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`);
  if (options.params) {
    for (const [k, v] of Object.entries(options.params)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    }
  }

  const buildHeaders = (token?: string | null): HeadersInit => ({
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  });

  const doFetch = (token?: string | null) => {
    const init: RequestInit = {
      method,
      headers: buildHeaders(token),
      signal: AbortSignal.timeout(10_000),
    };
    if (options.body !== undefined) {
      init.body = JSON.stringify(options.body);
    }
    return fetch(url.toString(), init);
  };

  let accessToken = options.skipAuth ? null : getAuthStore().accessToken;
  let res = await doFetch(accessToken);

  // On 401, attempt one silent token refresh then retry
  if (res.status === 401 && !options.skipAuth) {
    try {
      accessToken = await refreshAccessToken();
      res = await doFetch(accessToken);
    } catch {
      // Refresh failed — caller will receive the 401 ApiError
    }
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.clone().json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Non-JSON error body — fall back to statusText.
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  return params !== undefined
    ? request<T>("GET", path, { params })
    : request<T>("GET", path);
}

function post<T>(path: string, body: unknown, skipAuth = false): Promise<T> {
  return request<T>("POST", path, { body, skipAuth });
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>("PATCH", path, { body });
}

function del<T>(path: string): Promise<T> {
  return request<T>("DELETE", path);
}

// ── Auth endpoints ────────────────────────────────────────────────────────────

export interface LoginCredentials {
  email: string;
  password: string;
}

export async function login(credentials: LoginCredentials): Promise<BackendLoginResponse> {
  return post<BackendLoginResponse>("/v1/auth/login", credentials, true);
}

export interface MessageResponse {
  message: string;
}

/** Anti-enumeration: resolves with a generic message whether or not the email exists. */
export async function requestPasswordReset(email: string): Promise<MessageResponse> {
  return post<MessageResponse>("/v1/auth/request-password-reset", { email }, true);
}

export async function resetPassword(token: string, newPassword: string): Promise<MessageResponse> {
  return post<MessageResponse>("/v1/auth/reset-password", { token, new_password: newPassword }, true);
}

export async function verifyEmail(token: string): Promise<MessageResponse> {
  return post<MessageResponse>("/v1/auth/verify-email", { token }, true);
}

export async function logout(): Promise<void> {
  try {
    await request<void>("POST", "/v1/auth/logout", { body: {} });
  } catch {
    // Best-effort — clear local state regardless of server response
  } finally {
    getAuthStore().clearAuth();
  }
}

export async function getMe(): Promise<BackendUserPublic> {
  return get<BackendUserPublic>("/v1/auth/me");
}

/** EP-21.3 — marks the first-time onboarding wizard as completed for the current user. */
export async function completeOnboarding(): Promise<BackendUserPublic> {
  return post<BackendUserPublic>("/v1/auth/onboarding/complete", {});
}

// ── Settings — Profile / Preferences / Password / Account (EP-22.2) ──────────

export interface UpdateProfileBody {
  display_name?: string;
  username?: string | null;
  avatar_url?: string | null;
  bio?: string | null;
  timezone?: string;
}

export async function updateProfile(body: UpdateProfileBody): Promise<BackendUserPublic> {
  return patch<BackendUserPublic>("/v1/auth/me", body);
}

export async function updatePreferences(
  preferences: Record<string, unknown>,
): Promise<BackendUserPublic> {
  return patch<BackendUserPublic>("/v1/auth/me/preferences", { preferences });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<MessageResponse> {
  return post<MessageResponse>("/v1/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export async function deleteAccount(password: string): Promise<void> {
  return request<void>("DELETE", "/v1/auth/me", { body: { password } });
}

// ── Organizations endpoint (EP-12.1) ──────────────────────────────────────────

export async function getOrganizations(): Promise<BackendOrganizationsResponse> {
  return get<BackendOrganizationsResponse>("/v1/organizations");
}

/** EP-21.3 onboarding Step 2, extended EP-22.2 Settings — Workspace section. */
export async function updateOrganization(
  organizationId: string,
  body: { name?: string; description?: string },
): Promise<BackendOrgMembershipItem> {
  return patch<BackendOrgMembershipItem>(`/v1/organizations/${organizationId}`, body);
}

/** EP-22.2 Settings — Danger Zone. Refuses (400) for the personal workspace. */
export async function deleteOrganization(organizationId: string): Promise<void> {
  return del<void>(`/v1/organizations/${organizationId}`);
}

// ── Member management (EP-13) ─────────────────────────────────────────────────

export interface Member {
  id: string;
  user_id: string | null;
  email: string;
  display_name: string | null;
  role: "owner" | "admin" | "member" | "viewer";
  status: "active" | "invited";
  created_at: string;
}

export interface MembersListResponse {
  members: Member[];
  total: number;
}

export async function listMembers(organizationId: string): Promise<MembersListResponse> {
  return get<MembersListResponse>(`/v1/organizations/${organizationId}/members`);
}

export async function inviteMember(
  organizationId: string,
  email: string,
  role: string,
): Promise<Member> {
  return post<Member>(`/v1/organizations/${organizationId}/members`, { email, role });
}

export async function updateMemberRole(
  organizationId: string,
  membershipId: string,
  role: string,
): Promise<Member> {
  return patch<Member>(`/v1/organizations/${organizationId}/members/${membershipId}`, { role });
}

export async function removeMember(organizationId: string, membershipId: string): Promise<void> {
  return del<void>(`/v1/organizations/${organizationId}/members/${membershipId}`);
}

// ── RBAC introspection (EP-13) ─────────────────────────────────────────────────

export interface RoleInfo {
  role: string;
  label: string;
  permissions: string[];
}

export interface RolesResponse {
  roles: RoleInfo[];
}

export interface PermissionInfo {
  permission: string;
  domain: string;
  action: string;
}

export interface PermissionsResponse {
  permissions: PermissionInfo[];
}

export async function listRoles(): Promise<RolesResponse> {
  return get<RolesResponse>("/v1/rbac/roles");
}

export async function listPermissions(): Promise<PermissionsResponse> {
  return get<PermissionsResponse>("/v1/rbac/permissions");
}

// ── Organization API keys (EP-14) ────────────────────────────────────────────

export interface ApiKey {
  id: string;
  name: string;
  description: string | null;
  prefix: string;
  permissions: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}

export interface ApiKeysListResponse {
  keys: ApiKey[];
  total: number;
}

export type ApiKeyExpiration = "never" | "30d" | "90d";

export interface ApiKeyCreatedResponse {
  id: string;
  api_key: string;
  prefix: string;
  name: string;
  permissions: string[];
  created_at: string;
  expires_at: string | null;
}

export async function listApiKeys(organizationId: string): Promise<ApiKeysListResponse> {
  return get<ApiKeysListResponse>(`/v1/organizations/${organizationId}/api-keys`);
}

export async function createApiKey(
  organizationId: string,
  body: { name: string; description?: string; permissions: string[]; expiration: ApiKeyExpiration },
): Promise<ApiKeyCreatedResponse> {
  return post<ApiKeyCreatedResponse>(`/v1/organizations/${organizationId}/api-keys`, body);
}

export async function revokeApiKey(organizationId: string, keyId: string): Promise<void> {
  return del<void>(`/v1/organizations/${organizationId}/api-keys/${keyId}`);
}

/** EP-22.2 Settings — API Keys section. Renames/redescribes an existing key. */
export async function updateApiKey(
  organizationId: string,
  keyId: string,
  body: { name?: string; description?: string },
): Promise<ApiKey> {
  return patch<ApiKey>(`/v1/organizations/${organizationId}/api-keys/${keyId}`, body);
}

// ── Projects CRUD (EP-23) ──────────────────────────────────────────────────────

export interface ProjectRecord {
  id: string;
  name: string;
  description: string | null;
  environment: "development" | "staging" | "production";
  budget: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectsCrudListResponse {
  projects: ProjectRecord[];
  total: number;
}

export async function listProjectsCrud(organizationId: string): Promise<ProjectsCrudListResponse> {
  return get<ProjectsCrudListResponse>(`/v1/organizations/${organizationId}/projects`);
}

export async function createProject(
  organizationId: string,
  body: { name: string; description?: string; environment?: string; budget?: string },
): Promise<ProjectRecord> {
  return post<ProjectRecord>(`/v1/organizations/${organizationId}/projects`, body);
}

export async function updateProject(
  organizationId: string,
  projectId: string,
  body: { name?: string; description?: string; environment?: string; budget?: string | null },
): Promise<ProjectRecord> {
  return patch<ProjectRecord>(`/v1/organizations/${organizationId}/projects/${projectId}`, body);
}

export async function deleteProject(organizationId: string, projectId: string): Promise<void> {
  return del<void>(`/v1/organizations/${organizationId}/projects/${projectId}`);
}

// ── Provider Connections CRUD + credentials (EP-22) ─────────────────────────────

export type ProviderValidationStatus =
  | "healthy"
  | "invalid_api_key"
  | "unauthorized"
  | "quota_exceeded"
  | "network_failure"
  | "timeout"
  | "provider_unavailable";

export interface ProviderConnectionRecord {
  id: string;
  provider_type: string;
  display_name: string;
  project_id: string | null;
  is_active: boolean;
  has_credential: boolean;
  masked_api_key: string | null; // e.g. "sk-********************************AbC" — never the real key
  base_url: string | null;
  health_status: "unknown" | "healthy" | "warning" | "critical" | "recovering";
  last_validation_status: ProviderValidationStatus | null;
  last_error: string | null;
  last_failure_at: string | null;
  last_recovery_at: string | null;
  consecutive_failure_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProviderConnectionsListResponse {
  connections: ProviderConnectionRecord[];
  total: number;
}

export async function listProviderConnections(
  organizationId: string,
): Promise<ProviderConnectionsListResponse> {
  return get<ProviderConnectionsListResponse>(
    `/v1/organizations/${organizationId}/provider-connections`,
  );
}

export async function createProviderConnection(
  organizationId: string,
  body: {
    provider_type: string;
    display_name: string;
    api_key?: string;
    base_url?: string;
    project_id?: string;
  },
): Promise<ProviderConnectionRecord> {
  return post<ProviderConnectionRecord>(
    `/v1/organizations/${organizationId}/provider-connections`,
    body,
  );
}

export async function updateProviderConnection(
  organizationId: string,
  connectionId: string,
  body: {
    display_name?: string;
    base_url?: string;
    project_id?: string | null;
    is_active?: boolean;
  },
): Promise<ProviderConnectionRecord> {
  return patch<ProviderConnectionRecord>(
    `/v1/organizations/${organizationId}/provider-connections/${connectionId}`,
    body,
  );
}

export async function deleteProviderConnection(
  organizationId: string,
  connectionId: string,
): Promise<void> {
  return del<void>(`/v1/organizations/${organizationId}/provider-connections/${connectionId}`);
}

export interface TestProviderConnectionResult {
  connection_id: string;
  provider_type: string;
  health_status: string;
  last_validation_status: ProviderValidationStatus;
  tested: boolean;
  detail: string;
}

export async function testProviderConnectionById(
  organizationId: string,
  connectionId: string,
): Promise<TestProviderConnectionResult> {
  return post<TestProviderConnectionResult>(
    `/v1/organizations/${organizationId}/provider-connections/${connectionId}/test`,
    {},
  );
}

export async function rotateProviderConnectionKey(
  organizationId: string,
  connectionId: string,
  apiKey: string,
): Promise<ProviderConnectionRecord> {
  return post<ProviderConnectionRecord>(
    `/v1/organizations/${organizationId}/provider-connections/${connectionId}/rotate`,
    { api_key: apiKey },
  );
}

// ── Usage synchronization (EP-23.3) ──────────────────────────────────────────

export type SyncRunStatus =
  | "never_synced"
  | "pending"
  | "running"
  | "success"
  | "failed";

export interface CostImportedItem {
  currency: string;
  total_cost: string;
  record_count: number;
}

export interface SyncStatusResponse {
  connection_id: string;
  provider_type: string;
  sync_status: SyncRunStatus;
  last_sync_started_at: string | null;
  last_sync_completed_at: string | null;
  last_successful_sync_at: string | null;
  last_error: string | null;
  last_imported_at: string | null;
  records_imported: number;
  tokens_imported: number;
  estimated_cost_imported: CostImportedItem[];
  supports_usage_sync: boolean;
}

export interface SyncRunResponse {
  run_id: string;
  connection_id: string;
  provider_type: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  records_imported: number;
  records_failed: number;
  error_message: string | null;
}

export interface TriggerSyncResponse {
  run: SyncRunResponse;
  sync_status: SyncStatusResponse;
}

export interface SyncAllResponse {
  runs: SyncRunResponse[];
  total: number;
  succeeded: number;
  failed: number;
}

export async function getProviderConnectionSyncStatus(
  organizationId: string,
  connectionId: string,
): Promise<SyncStatusResponse> {
  return get<SyncStatusResponse>(
    `/v1/organizations/${organizationId}/provider-connections/${connectionId}/sync-status`,
  );
}

export async function syncProviderConnection(
  organizationId: string,
  connectionId: string,
): Promise<TriggerSyncResponse> {
  return post<TriggerSyncResponse>(
    `/v1/organizations/${organizationId}/provider-connections/${connectionId}/sync`,
    {},
  );
}

export async function syncAllProviderConnections(
  organizationId: string,
): Promise<SyncAllResponse> {
  return post<SyncAllResponse>(
    `/v1/organizations/${organizationId}/provider-connections/sync`,
    {},
  );
}

// ── Background sync scheduler (EP-23.4) ──────────────────────────────────────

export type SchedulerInterval = "5m" | "15m" | "1h" | "6h" | "24h";

export interface SchedulerJobItem {
  job_id: string;
  organization_id: string;
  status: "queued" | "running" | "completed" | "failed";
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  connections_synced: number;
  connections_failed: number;
  records_imported: number;
  retry_count: number;
  duration_seconds: number | null;
  error: string | null;
}

export interface SchedulerMonitoringSnapshot {
  is_running: boolean;
  active_jobs: number;
  queued_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  average_duration_seconds: number | null;
  last_execution: string | null;
}

export interface SchedulerStatusResponse {
  organization_id: string;
  auto_sync_enabled: boolean;
  interval: SchedulerInterval;
  interval_seconds: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  next_sync_at: string | null;
  current_job: SchedulerJobItem | null;
  scheduler_health: "healthy" | "degraded" | "disabled" | "not_running";
  monitoring: SchedulerMonitoringSnapshot;
}

export interface SchedulerJobsResponse {
  jobs: SchedulerJobItem[];
  total: number;
}

export async function getSchedulerStatus(organizationId: string): Promise<SchedulerStatusResponse> {
  return get<SchedulerStatusResponse>(
    `/v1/organizations/${organizationId}/provider-connections/scheduler/status`,
  );
}

export async function updateSchedulerSettings(
  organizationId: string,
  body: { auto_sync_enabled?: boolean; interval?: SchedulerInterval },
): Promise<SchedulerStatusResponse> {
  return patch<SchedulerStatusResponse>(
    `/v1/organizations/${organizationId}/provider-connections/scheduler/settings`,
    body,
  );
}

export async function getSchedulerJobs(
  organizationId: string,
  limit = 20,
): Promise<SchedulerJobsResponse> {
  return get<SchedulerJobsResponse>(
    `/v1/organizations/${organizationId}/provider-connections/scheduler/jobs?limit=${limit}`,
  );
}

// ── Provider connection intelligence (EP-07) ─────────────────────────────────

export interface ProviderConnectionStatus {
  is_connected: boolean;
  health_status: string;
  latency_ms: number | null;
  error_message: string | null;
  checked_at: string;
}

export interface TestConnectionResponse {
  provider: string;
  status: ProviderConnectionStatus;
  auth_valid: boolean;
}

export interface ProviderModelMetadata {
  id: string;
  display_name: string;
  provider_type: string;
  context_window: number | null;
  max_output_tokens: number | null;
  capabilities: string[];
  input_cost_per_1k: number | null;
  output_cost_per_1k: number | null;
  is_deprecated: boolean;
}

export interface ProviderModelsResponse {
  provider: string;
  models: ProviderModelMetadata[];
  count: number;
}

export interface ProviderInfoResponse {
  provider: string;
  display_name: string;
  version: string;
  api_version: string | null;
  authentication_type: string;
  documentation_url: string | null;
  health: string;
  supports_streaming: boolean;
  supports_tool_calling: boolean;
  supports_vision: boolean;
  supports_usage_api: boolean;
  supports_fine_tuning: boolean;
  max_context_window: number | null;
  supported_model_ids: string[];
}

export async function getProviderInfo(provider: string): Promise<ProviderInfoResponse> {
  return get<ProviderInfoResponse>(`/v1/providers/${provider}/info`);
}

export async function testProviderConnection(provider: string): Promise<TestConnectionResponse> {
  return post<TestConnectionResponse>(`/v1/providers/${provider}/test`, {});
}

export async function getProviderModels(provider: string): Promise<ProviderModelsResponse> {
  return get<ProviderModelsResponse>(`/v1/providers/${provider}/models`);
}

// ── Pricing catalog + calculator (EP-09) ─────────────────────────────────────

export interface ModelPricingRecord {
  id: string;
  external_id: string;
  provider: string;
  model: string;
  version: string;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  prompt_token_price: string;
  completion_token_price: string;
  cached_token_price: string | null;
  is_active: boolean;
}

export interface ModelPricingListResponse {
  items: ModelPricingRecord[];
  total: number;
  has_more: boolean;
}

export interface PriceCalculationResult {
  provider: string;
  model: string;
  currency: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number | null;
  total_tokens: number;
  prompt_cost: string;
  completion_cost: string;
  cached_cost: string | null;
  total_cost: string;
  pricing_date: string;
}

export async function listModelPricing(organizationId: string, limit = 100): Promise<ModelPricingListResponse> {
  return get<ModelPricingListResponse>("/v1/pricing/models", {
    organization_id: organizationId,
    limit: String(limit),
  });
}

export async function listPricingProviders(): Promise<string[]> {
  return get<string[]>("/v1/pricing/providers");
}

export async function calculatePrice(body: {
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens?: number;
}): Promise<PriceCalculationResult> {
  return post<PriceCalculationResult>("/v1/pricing/calculate", body);
}

// ── Dashboard params ──────────────────────────────────────────────────────────

export interface OverviewParams {
  organization_id: string;
  start_date: string;
  end_date: string;
  currency?: Currency;
  // EP-24.1 — optional dimension filters, supported by every breakdown endpoint
  project_id?: string;
  provider?: string;
  model?: string;
}

export interface TimeSeriesParams extends OverviewParams {
  granularity?: Granularity;
}

// ── Dashboard endpoints ───────────────────────────────────────────────────────

export async function getOverview(params: OverviewParams): Promise<OverviewKPIs> {
  if (USE_MOCK) {
    await delay(320);
    return getMockOverview(params.start_date, params.end_date);
  }
  const raw = await get<BackendOverviewResponse>(
    "/v1/dashboard/overview",
    params as unknown as Record<string, string>,
  );
  return mapOverview(raw);
}

export async function getTimeSeries(params: TimeSeriesParams): Promise<TimeSeriesResponse> {
  if (USE_MOCK) {
    await delay(400);
    return getMockTimeSeries(params.start_date, params.end_date, params.granularity);
  }
  const raw = await get<BackendTimeSeriesResponse>(
    "/v1/dashboard/time-series",
    params as unknown as Record<string, string>,
  );
  return mapTimeSeries(raw);
}

export async function getProviders(params: OverviewParams): Promise<ProvidersResponse> {
  if (USE_MOCK) {
    await delay(280);
    return getMockProviders(params.start_date, params.end_date);
  }
  const raw = await get<BackendProviderBreakdownResponse>(
    "/v1/dashboard/providers",
    params as unknown as Record<string, string>,
  );
  return mapProviders(raw);
}

export async function getModels(params: OverviewParams): Promise<ModelsResponse> {
  if (USE_MOCK) {
    await delay(350);
    return getMockModels(params.start_date, params.end_date);
  }
  const raw = await get<BackendModelBreakdownResponse>(
    "/v1/dashboard/models",
    params as unknown as Record<string, string>,
  );
  return mapModels(raw);
}

export async function getProjects(params: OverviewParams): Promise<ProjectsResponse> {
  if (USE_MOCK) {
    await delay(300);
    return getMockProjects();
  }
  const raw = await get<BackendProjectBreakdownResponse>(
    "/v1/dashboard/projects",
    params as unknown as Record<string, string>,
  );
  return mapProjects(raw);
}

export async function getOrganization(params: OverviewParams): Promise<OrganizationResponse> {
  if (USE_MOCK) {
    await delay(280);
    return getMockOrganization();
  }
  const raw = await get<BackendOrganizationDashboardResponse>(
    "/v1/dashboard/organization",
    params as unknown as Record<string, string>,
  );
  return mapOrganization(raw);
}

export async function getKPIs(params: OverviewParams): Promise<KPIsResponse> {
  if (USE_MOCK) {
    await delay(200);
    return getMockKPIs();
  }
  const raw = await get<BackendKPIResponse>(
    "/v1/dashboard/kpis",
    params as unknown as Record<string, string>,
  );
  return mapKPIs(raw);
}

// Recent activity — backend returns HTTP 501 NOT IMPLEMENTED.
// In live mode, returns an empty response so the UI shows an empty state.
// NOTE: this is GET /v1/usage/events (individual raw events), a different,
// still-unimplemented endpoint from GET /v1/dashboard/activity (imports/
// syncs/failures) below — see getActivityFeed for the real EP-24.1 feed.
export async function getRecentActivity(limit = 20): Promise<UsageEventsResponse> {
  if (USE_MOCK) {
    await delay(250);
    return getMockRecentActivity(limit);
  }
  // GET /v1/usage/events is 501 NOT IMPLEMENTED — return empty gracefully
  return { events: [], total: 0, page: 1, page_size: limit };
}

// EP-24.1 — hour-of-day x day-of-week usage heatmap
export async function getHeatmap(params: OverviewParams): Promise<HeatmapResponse> {
  if (USE_MOCK) {
    await delay(280);
    return getMockHeatmap();
  }
  const raw = await get<BackendHeatmapResponse>(
    "/v1/dashboard/heatmap",
    params as unknown as Record<string, string>,
  );
  return mapHeatmap(raw);
}

// EP-24.1 — real recent activity feed (imports/syncs/provider failures),
// backed by GET /v1/dashboard/activity — reuses EP-08/EP-23.3/EP-23.4's
// UsageCollectionRun + EP-22's ProviderConnection failure fields.
export async function getActivityFeed(
  organizationId: string,
  limit = 20,
): Promise<ActivityFeed> {
  if (USE_MOCK) {
    await delay(220);
    return getMockActivityFeed(limit);
  }
  const raw = await get<BackendActivityResponse>("/v1/dashboard/activity", {
    organization_id: organizationId,
    limit: String(limit),
  });
  return mapActivity(raw);
}

// ── Budgets (EP-24.2) ────────────────────────────────────────────────────────

export type BudgetScopeType = "organization" | "project" | "provider" | "model";
export type BudgetPeriodType = "daily" | "weekly" | "monthly" | "yearly" | "custom";
export type BudgetStatusLevel = "healthy" | "warning" | "critical" | "exceeded";

export interface BudgetRecord {
  id: string;
  organization_id: string;
  name: string;
  scope_type: BudgetScopeType;
  scope_project_id: string | null;
  scope_provider: string | null;
  scope_model: string | null;
  amount: string;
  currency: string;
  period: BudgetPeriodType;
  custom_period_start: string | null;
  custom_period_end: string | null;
  threshold_percentages: number[];
  enabled: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface BudgetsListResponse {
  budgets: BudgetRecord[];
  total: number;
}

export interface BudgetStatusSummary {
  budget: BudgetRecord;
  current_spend: string;
  remaining: string;
  percent_used: number;
  period_start: string;
  period_end: string;
  days_elapsed: number;
  days_remaining: number;
  projected_period_spend: string;
  remaining_daily_allowance: string;
  status: BudgetStatusLevel;
  highest_threshold_crossed: number | null;
}

export interface BudgetSummaryResponse {
  budgets: BudgetStatusSummary[];
  currency: string;
  total_budgeted: string;
  total_spent: string;
  total_remaining: string;
  active_alert_count: number;
  critical_alert_count: number;
  projected_eom_spend: string;
}

export interface CreateBudgetRequest {
  name: string;
  scope_type: BudgetScopeType;
  scope_project_id?: string | null;
  scope_provider?: string | null;
  scope_model?: string | null;
  amount: string;
  currency?: string;
  period: BudgetPeriodType;
  custom_period_start?: string | null;
  custom_period_end?: string | null;
  threshold_percentages?: number[];
  enabled?: boolean;
}

export interface UpdateBudgetRequest {
  name?: string;
  amount?: string;
  currency?: string;
  period?: BudgetPeriodType;
  custom_period_start?: string | null;
  custom_period_end?: string | null;
  threshold_percentages?: number[];
  enabled?: boolean;
}

export async function listBudgets(organizationId: string): Promise<BudgetsListResponse> {
  return get<BudgetsListResponse>("/v1/budgets", { organization_id: organizationId });
}

export async function createBudget(
  organizationId: string,
  body: CreateBudgetRequest,
): Promise<BudgetRecord> {
  return request<BudgetRecord>("POST", "/v1/budgets", {
    params: { organization_id: organizationId },
    body,
  });
}

export async function updateBudget(
  organizationId: string,
  budgetId: string,
  body: UpdateBudgetRequest,
): Promise<BudgetRecord> {
  return request<BudgetRecord>("PATCH", `/v1/budgets/${budgetId}`, {
    params: { organization_id: organizationId },
    body,
  });
}

export async function deleteBudget(organizationId: string, budgetId: string): Promise<void> {
  return request<void>("DELETE", `/v1/budgets/${budgetId}`, {
    params: { organization_id: organizationId },
  });
}

export async function getBudgetStatus(
  organizationId: string,
  budgetId: string,
): Promise<BudgetStatusSummary> {
  return get<BudgetStatusSummary>(`/v1/budgets/${budgetId}/status`, {
    organization_id: organizationId,
  });
}

export async function getBudgetSummary(
  organizationId: string,
  currency = "USD",
): Promise<BudgetSummaryResponse> {
  return get<BudgetSummaryResponse>("/v1/dashboard/budget-summary", {
    organization_id: organizationId,
    currency,
  });
}

// ── Alerts (EP-19.3) ─────────────────────────────────────────────────────────

export type AlertApiStatus = "open" | "acknowledged" | "resolved" | "dismissed";
export type AlertApiSeverity = "info" | "low" | "medium" | "high" | "critical";

export interface AlertRecord {
  id: string;
  alert_type: string;
  severity: AlertApiSeverity;
  status: AlertApiStatus;
  title: string;
  message: string;
  source: string;
  occurrence_count: number;
  metadata: Record<string, unknown>;
  first_occurred_at: string;
  last_occurred_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  acknowledgement_reason: string | null;
  resolved_at: string | null;
  dismissed_at: string | null;
  created_at: string;
}

export interface AlertsListResponse {
  alerts: AlertRecord[];
  total: number;
}

export interface ListAlertsParams {
  organizationId: string;
  status?: AlertApiStatus;
  severity?: AlertApiSeverity;
  alertType?: string;
  since?: string;
  until?: string;
  search?: string;
  limit?: number;
}

/** Persisted alert history — search/filter over what the backend's alert
 * engine has actually fired (budget/membership/API-key triggers as of this
 * EP; see backend/docs/realtime/ALERT_ARCHITECTURE.md for the full
 * accounting). Distinct from `useAlerts()`'s client-derived + live-merged
 * feed, which stays as-is; this is the "View history" / search surface. */
export async function listAlerts(params: ListAlertsParams): Promise<AlertsListResponse> {
  return get<AlertsListResponse>("/v1/alerts", {
    organization_id: params.organizationId,
    status: params.status,
    severity: params.severity,
    alert_type: params.alertType,
    since: params.since,
    until: params.until,
    search: params.search,
    limit: params.limit ? String(params.limit) : undefined,
  });
}

export async function acknowledgeAlert(
  organizationId: string,
  alertId: string,
  reason?: string,
): Promise<AlertRecord> {
  return request<AlertRecord>("POST", `/v1/alerts/${alertId}/acknowledge`, {
    params: { organization_id: organizationId },
    body: { reason: reason ?? null },
  });
}

export async function resolveAlert(organizationId: string, alertId: string): Promise<AlertRecord> {
  return request<AlertRecord>("POST", `/v1/alerts/${alertId}/resolve`, {
    params: { organization_id: organizationId },
  });
}

export async function dismissAlert(organizationId: string, alertId: string): Promise<AlertRecord> {
  return request<AlertRecord>("POST", `/v1/alerts/${alertId}/dismiss`, {
    params: { organization_id: organizationId },
  });
}

export async function reopenAlert(organizationId: string, alertId: string): Promise<AlertRecord> {
  return request<AlertRecord>("POST", `/v1/alerts/${alertId}/reopen`, {
    params: { organization_id: organizationId },
  });
}

export interface AlertPreferences {
  enabled_alert_types: string[];
  min_severity: AlertApiSeverity;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  timezone: string;
  daily_digest: boolean;
  immediate_notifications: boolean;
  max_notifications: number | null;
}

export async function getAlertPreferences(organizationId: string): Promise<AlertPreferences> {
  return get<AlertPreferences>("/v1/alerts/preferences", { organization_id: organizationId });
}

export async function updateAlertPreferences(
  organizationId: string,
  body: Partial<AlertPreferences>,
): Promise<AlertPreferences> {
  return patch<AlertPreferences>(
    `/v1/alerts/preferences?organization_id=${encodeURIComponent(organizationId)}`,
    body,
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
