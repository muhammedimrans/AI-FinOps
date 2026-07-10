import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Building2, AlertCircle, Loader2 } from "lucide-react";
import { getOrganizations } from "../services/api";
import { useOrgStore } from "../stores/org";
import type { BackendOrgMembershipItem } from "../types/backend";
import { CostorahMark } from "./CostorahLogo";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "empty" }
  | { status: "picker"; orgs: BackendOrgMembershipItem[] };

export default function OrgSelector() {
  const { setOrganization } = useOrgStore();
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getOrganizations()
      .then((data) => {
        if (cancelled) return;
        // EP-25.1 — the hidden personal workspace is never a switchable
        // option: a Business account's own personal org (every account has
        // exactly one, is_personal=true) is filtered out here so the picker
        // only ever shows real, collaborative workspaces. A pure Personal
        // account has zero business orgs after this filter, which is
        // exactly the "auto-select the one org silently" case below —
        // there is nothing to pick between.
        const businessOrgs = data.organizations.filter((o) => !o.is_personal);
        if (businessOrgs.length === 1) {
          const only = businessOrgs[0]!;
          setOrganization(only.id, only.name, false);
        } else if (businessOrgs.length > 1) {
          setState({ status: "picker", orgs: businessOrgs });
        } else {
          const personalOrg = data.organizations.find((o) => o.is_personal);
          if (personalOrg) {
            setOrganization(personalOrg.id, personalOrg.name, true);
          } else {
            setState({ status: "empty" });
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ status: "error", message: "Could not load organizations. Please refresh." });
        }
      });
    return () => { cancelled = true; };
  }, [setOrganization]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-app-bg p-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-brand-radial pointer-events-none" />
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="w-full max-w-sm relative z-10"
      >
        <div className="flex items-center gap-2.5 justify-center mb-6">
          <CostorahMark className="w-8 h-8" />
          <span className="font-display text-sm font-bold tracking-[0.12em] text-tx-primary">COSTORAH</span>
        </div>

        <div className="glass-panel shadow-glow-brand p-8">
          <div className="w-10 h-10 rounded-xl bg-brand-subtle flex items-center justify-center mb-5">
            <Building2 size={18} className="text-brand" />
          </div>

          {state.status === "loading" && (
            <div className="flex items-center gap-3 text-tx-muted text-sm">
              <Loader2 size={16} className="animate-spin text-brand" />
              Loading organizations…
            </div>
          )}

          {state.status === "error" && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-danger-dim border border-danger/20">
              <AlertCircle size={14} className="text-danger mt-0.5 flex-shrink-0" />
              <p className="text-xs text-danger">{state.message}</p>
            </div>
          )}

          {state.status === "empty" && (
            <>
              <h1 className="text-lg font-bold text-tx-primary mb-1">No organizations</h1>
              <p className="text-sm text-tx-muted">
                Your account is not a member of any organization. Contact your administrator to
                be added to one.
              </p>
            </>
          )}

          {state.status === "picker" && (
            <>
              <h1 className="text-lg font-bold text-tx-primary mb-1">Select organization</h1>
              <p className="text-sm text-tx-muted mb-4">Choose an organization to continue.</p>
              <div className="space-y-2">
                {state.orgs.map((org) => (
                  <button
                    key={org.id}
                    onClick={() => setOrganization(org.id, org.name, org.is_personal)}
                    className="w-full text-left px-4 py-3 rounded-lg border border-border-subtle
                               bg-app-bg/60 hover:bg-brand-subtle hover:border-brand/40
                               transition-colors duration-fast group"
                  >
                    <p className="text-sm font-medium text-tx-primary group-hover:text-brand">
                      {org.name}
                    </p>
                    <p className="text-xs text-tx-muted mt-0.5 capitalize">{org.role}</p>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
