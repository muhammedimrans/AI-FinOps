import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  status: string;
  email_verified: boolean;
}

interface AuthState {
  // Access token lives in memory only — NOT persisted to localStorage.
  // On page reload it is null; ProtectedRoute will re-obtain it via the refresh token.
  accessToken: string | null;

  // Refresh token and user info ARE persisted so the session survives page reloads.
  refreshToken: string | null;
  user: AuthUser | null;

  setLogin: (accessToken: string, refreshToken: string, user: AuthUser) => void;
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

      setLogin: (accessToken, refreshToken, user) =>
        set({ accessToken, refreshToken, user }),

      setAccessToken: (accessToken) => set({ accessToken }),

      updateUser: (patch) => set((s) => ({ user: s.user ? { ...s.user, ...patch } : s.user })),

      clearAuth: () => set({ accessToken: null, refreshToken: null, user: null }),

      isAuthenticated: () => get().accessToken !== null,
    }),
    {
      name: "ai-finops-auth",
      partialize: (s) => ({
        // Persist only what survives page reload.
        // accessToken intentionally excluded — memory-only for XSS mitigation.
        refreshToken: s.refreshToken,
        user: s.user,
      }),
    },
  ),
);
