import { type FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { Building2, AlertCircle } from "lucide-react";
import { useOrgStore } from "../stores/org";

// Temporary UI shown when no organization_id is available.
//
// ROOT CAUSE: The backend login response does not return organization membership.
// This prompt will be removed once the backend adds GET /v1/organizations (see
// docs/backend-contracts/ORG-CONTEXT-CONTRACT.md). Until then, users must paste
// their Organization UUID to proceed.
export default function OrgPrompt() {
  const { setOrganization } = useOrgStore();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const UUID_RE =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!UUID_RE.test(trimmed)) {
      setError("Please enter a valid UUID (e.g. 123e4567-e89b-12d3-a456-426614174000).");
      return;
    }
    setOrganization(trimmed);
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-app-bg p-4">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="glass-card border border-border-subtle p-8">
          <div className="w-10 h-10 rounded-xl bg-warning-dim flex items-center justify-center mb-5">
            <Building2 size={18} className="text-warning-light" />
          </div>
          <h1 className="text-lg font-bold text-tx-primary mb-1">Select organization</h1>
          <p className="text-sm text-tx-muted mb-1">
            Enter your Organization ID to continue.
          </p>
          <p className="text-xs text-tx-muted mb-6 p-3 rounded-lg bg-app-bg border border-border-subtle">
            <strong className="text-tx-secondary">Note:</strong> The backend does not yet return
            organization membership at login. This field will be auto-populated once{" "}
            <code className="font-mono">GET /v1/organizations</code> is implemented.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="org-id"
                className="block text-xs font-medium text-tx-secondary mb-1.5"
              >
                Organization UUID
              </label>
              <input
                id="org-id"
                type="text"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                  setError(null);
                }}
                className="w-full px-3 py-2 text-sm font-mono bg-app-bg border border-border-subtle
                           rounded-lg text-tx-primary placeholder:text-tx-muted
                           focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60
                           transition-colors duration-150"
              />
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-danger-dim border border-danger/20">
                <AlertCircle size={14} className="text-danger mt-0.5 flex-shrink-0" />
                <p className="text-xs text-danger">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={!value.trim()}
              className="w-full h-9 rounded-lg bg-primary hover:bg-primary/90 text-white text-sm
                         font-medium transition-colors duration-150 disabled:opacity-50
                         disabled:cursor-not-allowed"
            >
              Continue
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}
