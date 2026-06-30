import { create } from "zustand";
import { persist } from "zustand/middleware";

// Organization context store.
//
// BACKEND GAP (see docs/backend-contracts/ORG-CONTEXT-CONTRACT.md):
// The backend login response does not include organization membership.
// organizationId must be set by an explicit user action (org switcher or
// manual entry) or injected once the backend adds GET /v1/organizations.
// All dashboard queries are disabled while organizationId is null.

interface OrgState {
  organizationId: string | null;
  organizationName: string | null;

  setOrganization: (id: string, name?: string) => void;
  clearOrganization: () => void;
}

export const useOrgStore = create<OrgState>()(
  persist(
    (set) => ({
      organizationId: null,
      organizationName: null,

      setOrganization: (organizationId, organizationName = "") =>
        set({ organizationId, organizationName }),

      clearOrganization: () =>
        set({ organizationId: null, organizationName: null }),
    }),
    {
      name: "ai-finops-org",
    },
  ),
);
