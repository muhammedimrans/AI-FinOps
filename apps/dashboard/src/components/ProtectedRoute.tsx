import { type ReactNode, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

interface Props {
  children: ReactNode;
}

// Attempts to obtain a valid access token silently using the persisted refresh token.
// Shows nothing while the check is in progress to avoid a flash of the login redirect.
export default function ProtectedRoute({ children }: Props) {
  const { accessToken, refreshToken, setLogin, clearAuth, user } = useAuthStore();
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

  return <>{children}</>;
}
