import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Read/dismiss-state for alerts. Alert ids are deterministic for
 * client-derived alerts (e.g. "budget-over:<project_id>", "anomaly:<date>")
 * and are each live event's `event_id` for real-time-sourced alerts — both
 * kinds share this one store so a dismissed/read alert stays that way
 * across reloads. The alerts themselves come from hooks/useAlerts (derived
 * from cached dashboard data, merged with live notification-shaped
 * real-time events) — this store only tracks what the user has done with
 * each one.
 */
interface NotificationState {
  readIds: Record<string, true>;
  dismissedIds: Record<string, true>;
  markRead: (id: string) => void;
  markAllRead: (ids: string[]) => void;
  dismiss: (id: string) => void;
  clearAll: (ids: string[]) => void;
}

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set) => ({
      readIds: {},
      dismissedIds: {},
      markRead: (id) => set((s) => ({ readIds: { ...s.readIds, [id]: true } })),
      markAllRead: (ids) =>
        set((s) => ({
          readIds: { ...s.readIds, ...Object.fromEntries(ids.map((id) => [id, true] as const)) },
        })),
      dismiss: (id) => set((s) => ({ dismissedIds: { ...s.dismissedIds, [id]: true } })),
      clearAll: (ids) =>
        set((s) => ({
          dismissedIds: {
            ...s.dismissedIds,
            ...Object.fromEntries(ids.map((id) => [id, true] as const)),
          },
        })),
    }),
    { name: "costorah-notifications" },
  ),
);
