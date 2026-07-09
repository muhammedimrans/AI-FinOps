// Minimal fetch client for the backend's auth endpoints — EP-21.2.
//
// Deliberately cookie-based, not bearer-token: apps/website has no
// long-lived client state (no Zustand store, no protected routes to
// guard beyond these two forms), so it relies entirely on the
// httpOnly session cookie the backend sets on register/login
// (app/auth/cookies.py) rather than managing a token in JS. See
// CLAUDE.md §6.
//
// Deliberately NOT a copy of apps/dashboard/src/services/api.ts's
// request() wrapper: that one manages a Zustand-held bearer token and
// silent-refresh-on-401, neither of which applies here — a smaller,
// purpose-built client is more honest than reusing machinery for
// concerns this app doesn't have.

const BASE_URL: string =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

export const DASHBOARD_URL: string =
  (import.meta.env["VITE_DASHBOARD_URL"] as string | undefined) ?? "http://localhost:5173";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    credentials: "include", // required for the session cookie to be set/sent
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.clone().json()) as { detail?: string };
      if (data.detail) detail = data.detail;
    } catch {
      // Non-JSON error body — fall back to statusText.
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export interface UserPublic {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  status: string;
  email_verified: boolean;
}

export interface WorkspacePublic {
  id: string;
  name: string;
  slug: string;
  is_personal: boolean;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface RegisterResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserPublic;
  workspace: WorkspacePublic;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserPublic;
}

export function register(body: RegisterRequest): Promise<RegisterResponse> {
  return post<RegisterResponse>("/v1/auth/register", body);
}

export function login(body: LoginRequest): Promise<LoginResponse> {
  return post<LoginResponse>("/v1/auth/login", body);
}
