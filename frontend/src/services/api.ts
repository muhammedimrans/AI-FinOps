import type {
  OverviewKPIs,
  TimeSeriesResponse,
  ProvidersResponse,
  ModelsResponse,
  ProjectsResponse,
  OrganizationResponse,
  KPIsResponse,
  UsageEventsResponse,
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
  BackendLoginResponse,
  BackendTokenResponse,
  BackendOrganizationsResponse,
} from "../types/backend";
import {
  mapOverview,
  mapTimeSeries,
  mapProviders,
  mapModels,
  mapProjects,
  mapOrganization,
  mapKPIs,
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
  method: "GET" | "POST",
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
    throw new ApiError(res.status, `API ${res.status}: ${res.statusText}`);
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

// ── Organizations endpoint (EP-12.1) ──────────────────────────────────────────

export async function getOrganizations(): Promise<BackendOrganizationsResponse> {
  return get<BackendOrganizationsResponse>("/v1/organizations");
}

// ── Dashboard params ──────────────────────────────────────────────────────────

export interface OverviewParams {
  organization_id: string;
  start_date: string;
  end_date: string;
  currency?: Currency;
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
export async function getRecentActivity(limit = 20): Promise<UsageEventsResponse> {
  if (USE_MOCK) {
    await delay(250);
    return getMockRecentActivity(limit);
  }
  // GET /v1/usage/events is 501 NOT IMPLEMENTED — return empty gracefully
  return { events: [], total: 0, page: 1, page_size: limit };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
