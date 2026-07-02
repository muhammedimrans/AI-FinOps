import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Read-state for derived alerts. Alert ids are deterministic (e.g.
 * "budget-over:<project_id>", "anomaly:<date>") so a dismissed alert stays
 * read across reloads for as long as the underlying condition persists.
 * The alerts themselves are derived from live dashboard data in
 * hooks/useAlerts — this store only tracks which ones the user has seen.
 */
interface NotificationState {
  readIds: Record<string, true>;
  markRead: (id: string) => void;
  markAllRead: (ids: string[]) => void;
}

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set) => ({
      readIds: {},
      markRead: (id) => set((s) => ({ readIds: { ...s.readIds, [id]: true } })),
      markAllRead: (ids) =>
        set((s) => ({
          readIds: { ...s.readIds, ...Object.fromEntries(ids.map((id) => [id, true] as const)) },
        })),
    }),
    { name: "costorah-notifications" },
  ),
);
