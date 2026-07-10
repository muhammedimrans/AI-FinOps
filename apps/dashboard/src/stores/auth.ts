import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  status: string;
  email_verified: boolean;
  // EP-21.3: true once the first-time onboarding wizard (/onboarding) has
  // been completed. Optional/absent means "unknown" (e.g. a session
  // persisted before this field existed) — ProtectedRoute treats that the
  // same as false and lets the wizard run once to populate it for real.
  onboarding_completed?: boolean;
  // EP-22.2 Settings — optional/absent for a session persisted before these
  // fields existed, same "unknown, not missing" treatment as
  // onboarding_completed above; self-heals on the next /me refresh.
  avatar_url?: string | null;
  bio?: string | null;
  timezone?: string | null;
  created_at?: string;
  preferences?: Record<string, unknown>;
  // EP-24.5 Settings — "Linked accounts" section, same optional/self-heals
  // treatment as the EP-22.2 fields above.
  google_linked?: boolean;
  google_email?: string | null;
  last_login_provider?: string | null;
  // EP-24.6.1 — true once the account has a password set. Derived on the
  // backend from `password_hash is not None`, never a new column. A
  // Google-only account starts `false`; ProtectedRoute forces it through
  // /set-password before anything else. Same "absent/undefined means
  // unknown, never force a redirect" treatment as onboarding_completed —
  // a session persisted before this field existed self-heals on the next
  // silent refresh rather than being incorrectly trapped in the gate.
  password_configured?: boolean;
}

interface AuthState {
  // Access token lives in memory only — NOT persisted to localStorage.
  // On page reload it is null; ProtectedRoute will re-obtain it via the refresh token.
  accessToken: string | null;

  // Refresh token and user info are persisted so the session survives page
  // reloads — but only when the user chose "Remember me" at login.
  refreshToken: string | null;
  user: AuthUser | null;
  remember: boolean;

  setLogin: (accessToken: string, refreshToken: string, user: AuthUser, remember?: boolean) => void;
  setAccessToken: (token: string) => void;
  updateUser: (patch: Partial<AuthUser>) => void;
  clearAuth: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      remember: true,

      // `remember` is only passed by the login form; token-refresh flows omit
      // it and keep whatever the user chose when they signed in.
      setLogin: (accessToken, refreshToken, user, remember) =>
        set((s) => ({ accessToken, refreshToken, user, remember: remember ?? s.remember })),

      setAccessToken: (accessToken) => set({ accessToken }),

      updateUser: (patch) => set((s) => ({ user: s.user ? { ...s.user, ...patch } : s.user })),

      clearAuth: () => set({ accessToken: null, refreshToken: null, user: null }),

      isAuthenticated: () => get().accessToken !== null,
    }),
    {
      name: "ai-finops-auth",
      partialize: (s) =>
        // accessToken intentionally excluded — memory-only for XSS mitigation.
        // Without "Remember me", the refresh token stays memory-only too, so
        // closing the tab genuinely ends the session.
        s.remember
          ? { refreshToken: s.refreshToken, user: s.user, remember: s.remember }
          : { remember: s.remember },
    },
  ),
);
