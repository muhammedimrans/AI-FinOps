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
  // EP-25.1 — whether the currently-selected organization is the account's
  // hidden personal workspace (Organization.is_personal). Drives every
  // "hide collaboration UI" decision in the dashboard shell (Sidebar nav,
  // Settings' Workspace tab, the org switcher) — sourced from the same
  // `is_personal` field GET /v1/organizations already returns, not a new
  // backend concept.
  isPersonal: boolean;
  // Keyed by organizationId so switching orgs doesn't mix up logos.
  organizationLogos: Record<string, string>;

  setOrganization: (id: string, name?: string, isPersonal?: boolean) => void;
  clearOrganization: () => void;
  setOrganizationLogo: (organizationId: string, dataUrl: string | null) => void;
}

export const useOrgStore = create<OrgState>()(
  persist(
    (set) => ({
      organizationId: null,
      organizationName: null,
      isPersonal: false,
      organizationLogos: {},

      setOrganization: (organizationId, organizationName = "", isPersonal = false) =>
        set({ organizationId, organizationName, isPersonal }),

      clearOrganization: () =>
        set({ organizationId: null, organizationName: null, isPersonal: false }),

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
