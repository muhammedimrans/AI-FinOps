import { create } from "zustand";
import { persist } from "zustand/middleware";

interface OnboardingState {
  completed: boolean;
  complete: () => void;
}

/** Tracks whether the first-run welcome flow has been shown/dismissed, persisted per browser. */
export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      completed: false,
      complete: () => set({ completed: true }),
    }),
    { name: "costorah-onboarding" },
  ),
);
