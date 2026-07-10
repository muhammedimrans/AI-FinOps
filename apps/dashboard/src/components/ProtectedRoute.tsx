import { type ReactNode, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { getMe } from "../services/api";

interface Props {
  children: ReactNode;
}

// Attempts to obtain a valid access token silently using the persisted refresh token.
// Shows nothing while the check is in progress to avoid a flash of the login redirect.
export default function ProtectedRoute({ children }: Props) {
  const { accessToken, refreshToken, setLogin, updateUser, clearAuth, user } = useAuthStore();
  const location = useLocation();
  const [checking, setChecking] = useState(!accessToken && !!refreshToken);

  useEffect(() => {
    if (accessToken || !refreshToken) {
      setChecking(false);
      return;
    }

    // Access token is gone (page reload) but refresh token exists — try silent refresh.
    void (async () => {
      try {
        const res = await fetch(
          `${(import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000"}/v1/auth/refresh`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
            signal: AbortSignal.timeout(10_000),
          },
        );
        if (!res.ok) {
          clearAuth();
          return;
        }
        const data = (await res.json()) as {
          access_token: string;
          refresh_token: string;
          token_type: string;
          expires_in: number;
        };
        // user is still in persisted store; only tokens change
        setLogin(data.access_token, data.refresh_token, user!);

        // EP-21.3: refresh runs on every reload, so this is also the cheapest
        // place to heal a persisted user object that predates
        // onboarding_completed (or any other field added after the session
        // was created) — best-effort, a failure here shouldn't block access.
        try {
          const me = await getMe();
          updateUser({
            onboarding_completed: me.onboarding_completed,
            password_configured: me.password_configured,
          });
        } catch {
          // ignore — stale field self-heals on the next successful refresh
        }
      } catch {
        clearAuth();
      } finally {
        setChecking(false);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once on mount

  if (checking) {
    // Blank during silent token refresh to avoid flickering the login redirect
    return null;
  }

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  // EP-24.6.1 (Issue 1): a Google-only account must set a password before
  // reaching anything else — checked *before* the onboarding gate below, so
  // a first-time Google signup lands on /set-password first, then flows
  // into /onboarding on success, matching the spec's
  // "Google Authentication -> ... -> Set Password -> ... -> Welcome /
  // Onboarding" order. Same "undefined is unknown, don't force" treatment
  // as onboarding_completed — a session persisted before this field
  // existed self-heals via the refresh-time sync above rather than being
  // incorrectly trapped here.
  if (user?.password_configured === false && location.pathname !== "/set-password") {
    return <Navigate to="/set-password" replace />;
  }

  // EP-21.3: onboarding must run once, right after auth, regardless of entry
  // point (website registration handoff, website login handoff, or the
  // dashboard's own /login) — enforced here rather than at each call site so
  // there is exactly one place this rule can be gotten wrong. `undefined`
  // (unknown — e.g. a session persisted before this field existed) is not
  // forced into onboarding; it self-heals via the refresh-time sync above.
  //
  // `user?.password_configured !== false` guards against a redirect loop
  // (EP-24.6.1): a brand-new Google account can have *both*
  // `password_configured === false` and `onboarding_completed === false`
  // at once. Without this guard, the password gate above sends
  // "/dashboard" -> "/set-password", then this gate — seeing
  // `pathname !== "/onboarding"` is still true there — would immediately
  // bounce "/set-password" -> "/onboarding", which the password gate then
  // bounces straight back, forever. This gate simply stays out of the way
  // entirely until the password gate is satisfied.
  if (
    user?.onboarding_completed === false &&
    user?.password_configured !== false &&
    location.pathname !== "/onboarding"
  ) {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}
