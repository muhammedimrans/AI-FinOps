import { Fragment } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Check, Minus, ShieldCheck } from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import { listRoles, listPermissions } from "../services/api";
import { cn } from "../utils";

const ROLE_DESCRIPTIONS: Record<string, string> = {
  owner: "Full control, including billing and deleting the organization.",
  admin: "Manages members, projects, and providers, but not billing.",
  member: "Everyday access to usage, projects, and providers.",
  viewer: "Read-only access to dashboards and reports.",
};

export default function RBAC() {
  const rolesQuery = useQuery({ queryKey: ["rbac-roles"], queryFn: listRoles });
  const permissionsQuery = useQuery({ queryKey: ["rbac-permissions"], queryFn: listPermissions });

  const isLoading = rolesQuery.isLoading || permissionsQuery.isLoading;
  const isError = rolesQuery.isError || permissionsQuery.isError;
  const roles = rolesQuery.data?.roles ?? [];
  const permissions = permissionsQuery.data?.permissions ?? [];

  const domains = [...new Set(permissions.map((p) => p.domain))].sort();

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 sm:gap-6">
      <PageHeader
        title="Roles & Permissions"
        description="What each role can do in this organization. Role changes happen from the Users page."
      />

      {isLoading ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-24 skeleton rounded-card-lg" />)}
          </div>
          <div className="h-96 skeleton rounded-card-lg" />
        </>
      ) : isError ? (
        <Section>
          <EmptyState
            type="error"
            title="Couldn't load roles"
            description="Something went wrong while fetching the role and permission definitions."
          />
        </Section>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {roles.map((r, i) => (
              <motion.div
                key={r.role}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="glass-card rounded-card-lg border border-border-subtle p-4"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <ShieldCheck size={14} className="text-brand flex-shrink-0" />
                  <h3 className="text-sm font-semibold text-tx-primary">{r.label}</h3>
                </div>
                <p className="text-xs text-tx-muted leading-relaxed mb-2">
                  {ROLE_DESCRIPTIONS[r.role] ?? "Custom role."}
                </p>
                <p className="text-xs text-tx-secondary font-medium">
                  {r.permissions.length} permission{r.permissions.length === 1 ? "" : "s"}
                </p>
              </motion.div>
            ))}
          </div>

          <Section
            title="Permission matrix"
            description="Every permission the platform enforces, by role. Read-only."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-xs text-tx-muted">
                    <th className="px-5 py-3 font-medium">Permission</th>
                    {roles.map((r) => (
                      <th key={r.role} className="px-3 py-3 font-medium text-center">{r.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {domains.map((domain) => (
                    <Fragment key={domain}>
                      <tr className="bg-app-muted/40">
                        <td colSpan={roles.length + 1} className="px-5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-tx-muted">
                          {domain}
                        </td>
                      </tr>
                      {permissions
                        .filter((p) => p.domain === domain)
                        .map((p) => (
                          <tr key={p.permission} className="border-b border-border-subtle last:border-0">
                            <td className="px-5 py-2.5 text-tx-primary capitalize">{p.action}</td>
                            {roles.map((r) => {
                              const allowed = r.permissions.includes(p.permission);
                              return (
                                <td key={r.role} className="px-3 py-2.5 text-center">
                                  <span
                                    className={cn(
                                      "inline-flex w-5 h-5 rounded-md items-center justify-center",
                                      allowed ? "bg-success-dim text-success" : "text-tx-muted/40",
                                    )}
                                    aria-label={allowed ? `${r.label} can ${p.permission}` : `${r.label} cannot ${p.permission}`}
                                  >
                                    {allowed ? <Check size={12} /> : <Minus size={12} />}
                                  </span>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
