import { create } from "zustand";
import { persist } from "zustand/middleware";

// EP-25.4.4 Part 1/2 — preferences for the dashboard's Getting Started
// widget (features/Overview.tsx's OnboardingWidget). Distinct from
// stores/onboarding.ts (the one-time welcome/theme-picker popup) and from
// the backend's own `users.onboarding_completed_at` field (EP-21.3's
// /onboarding wizard) — this widget has no backend equivalent, so its
// state is honestly a per-browser preference, following the exact same
// zustand+persist convention stores/onboarding.ts already established.
//
// `neverShow` is persisted (survives reloads/new sessions) — cleared only
// by "Reset onboarding" in Settings > Preferences. `dismissed` is
// intentionally NOT persisted (see `partialize` below): dismissing hides
// the widget for the rest of this browser session only, so a genuinely
// incomplete setup doesn't disappear forever by accident.
//
// `visitedAnalytics` is a real, persisted signal — set once by
// features/Analytics.tsx on mount — used to auto-complete the checklist's
// "View Analytics" step (Part 2). This intentionally supersedes EP-22.3's
// original design note ("no separate 'has visited' flag... would be
// duplicate state") — this EP's own spec explicitly asks for exactly that
// signal, so the earlier decision is superseded here, not silently ignored.
interface OnboardingWidgetState {
  neverShow: boolean;
  dismissed: boolean;
  visitedAnalytics: boolean;
  dismiss: () => void;
  setNeverShow: (value: boolean) => void;
  markVisitedAnalytics: () => void;
  reset: () => void;
}

export const useOnboardingWidgetStore = create<OnboardingWidgetState>()(
  persist(
    (set) => ({
      neverShow: false,
      dismissed: false,
      visitedAnalytics: false,
      dismiss: () => set({ dismissed: true }),
      setNeverShow: (value) => set({ neverShow: value }),
      markVisitedAnalytics: () => set({ visitedAnalytics: true }),
      reset: () => set({ neverShow: false, dismissed: false, visitedAnalytics: false }),
    }),
    {
      name: "costorah-onboarding-widget",
      partialize: (state) => ({
        neverShow: state.neverShow,
        visitedAnalytics: state.visitedAnalytics,
      }),
    },
  ),
);
