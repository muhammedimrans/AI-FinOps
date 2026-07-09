import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Currency, Granularity } from "../types/api";
import { getToday, getDaysAgo } from "../utils";

interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;

  // Global filters
  currency: Currency;
  granularity: Granularity;
  datePreset: string;
  startDate: string;
  endDate: string;
  setCurrency: (c: Currency) => void;
  setGranularity: (g: Granularity) => void;
  setDateRange: (preset: string, start: string, end: string) => void;

  // Command palette
  commandOpen: boolean;
  setCommandOpen: (v: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),

      currency: "USD",
      granularity: "daily",
      datePreset: "30d",
      startDate: getDaysAgo(30),
      endDate: getToday(),
      setCurrency: (currency) => set({ currency }),
      setGranularity: (granularity) => set({ granularity }),
      setDateRange: (datePreset, startDate, endDate) =>
        set({ datePreset, startDate, endDate }),

      commandOpen: false,
      setCommandOpen: (commandOpen) => set({ commandOpen }),
    }),
    {
      name: "ai-finops-ui",
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        currency: s.currency,
        granularity: s.granularity,
        datePreset: s.datePreset,
        startDate: s.startDate,
        endDate: s.endDate,
      }),
    },
  ),
);
