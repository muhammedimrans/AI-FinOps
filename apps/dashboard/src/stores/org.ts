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
  // Keyed by organizationId so switching orgs doesn't mix up logos.
  organizationLogos: Record<string, string>;

  setOrganization: (id: string, name?: string) => void;
  clearOrganization: () => void;
  setOrganizationLogo: (organizationId: string, dataUrl: string | null) => void;
}

export const useOrgStore = create<OrgState>()(
  persist(
    (set) => ({
      organizationId: null,
      organizationName: null,
      organizationLogos: {},

      setOrganization: (organizationId, organizationName = "") =>
        set({ organizationId, organizationName }),

      clearOrganization: () =>
        set({ organizationId: null, organizationName: null }),

      setOrganizationLogo: (organizationId, dataUrl) =>
        set((s) => {
          const next = { ...s.organizationLogos };
          if (dataUrl) next[organizationId] = dataUrl;
          else delete next[organizationId];
          return { organizationLogos: next };
        }),
    }),
    {
      name: "ai-finops-org",
    },
  ),
);
