import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Building2, AlertCircle, Loader2 } from "lucide-react";
import { getOrganizations } from "../lib/api";
import { useOrgStore } from "../stores/org";
import type { BackendOrgMembershipItem } from "../types/backend";

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
        const orgs = data.organizations;
        if (orgs.length === 0) {
          setState({ status: "empty" });
        } else if (orgs.length === 1) {
          const only = orgs[0]!;
          setOrganization(only.id, only.name);
        } else {
          setState({ status: "picker", orgs });
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
    <div className="min-h-screen flex items-center justify-center bg-app-bg p-4">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="glass-card border border-border-subtle p-8">
          <div className="w-10 h-10 rounded-xl bg-primary-subtle flex items-center justify-center mb-5">
            <Building2 size={18} className="text-primary" />
          </div>

          {state.status === "loading" && (
            <div className="flex items-center gap-3 text-tx-muted text-sm">
              <Loader2 size={16} className="animate-spin text-primary" />
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
                    onClick={() => setOrganization(org.id, org.name)}
                    className="w-full text-left px-4 py-3 rounded-lg border border-border-subtle
                               bg-app-bg hover:bg-primary-subtle hover:border-primary/40
                               transition-colors duration-150 group"
                  >
                    <p className="text-sm font-medium text-tx-primary group-hover:text-primary">
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
