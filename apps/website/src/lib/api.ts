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
  onboarding_completed: boolean;
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

/**
 * Requests a fresh verification email (EP-24.4 / EP-24.4.1) — used from the
 * login form's "Resend verification email" affordance when a login attempt
 * is rejected with 403 for an unverified account. Anti-enumeration on the
 * backend: the response is the same generic message regardless of whether
 * the account exists or is already verified, so there is nothing to branch
 * on here beyond "the request completed."
 */
export function resendVerification(email: string): Promise<{ message: string }> {
  return post<{ message: string }>("/v1/auth/resend-verification", { email });
}

/**
 * URL for the "Continue with Google" button (EP-24.5) — a plain top-level
 * navigation (`<a href>`/`window.location.href`, never `fetch`), since the
 * backend's own GET /v1/auth/google/start sets an httpOnly state cookie and
 * 302s to Google's consent screen. The eventual callback redirects back to
 * DASHBOARD_URL with the session in the URL fragment, exactly like the
 * password-based register()/login() handoff above.
 */
export function googleOAuthStartUrl(): string {
  return `${BASE_URL}/v1/auth/google/start`;
}

/**
 * Builds the redirect URL that hands the session off to apps/dashboard.
 *
 * apps/dashboard authenticates via a Zustand-held bearer token, not the
 * httpOnly cookie this app relies on (CLAUDE.md §6 — migrating the
 * dashboard onto the cookie is tracked separately, not required for
 * EP-21.2). Until then, the token pair + user (+ workspace, on register)
 * travel in the URL *fragment*, which browsers never send to any server
 * — this is not the query-string "token in URL" pattern, it's the same
 * fragment-only technique OAuth's implicit flow used for exactly this
 * reason. apps/dashboard/src/lib/consumeSessionHandoff.ts reads it once
 * and clears it immediately.
 */
export function buildDashboardHandoffUrl(
  path: string,
  session: {
    access_token: string;
    refresh_token: string;
    user: UserPublic;
    workspace?: WorkspacePublic;
  },
): string {
  const payload = {
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    user: session.user,
    ...(session.workspace
      ? { workspace: { id: session.workspace.id, name: session.workspace.name } }
      : {}),
  };
  const encoded = encodeURIComponent(btoa(JSON.stringify(payload)));
  return `${DASHBOARD_URL}${path}#session=${encoded}`;
}
