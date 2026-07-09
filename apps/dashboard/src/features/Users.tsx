import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Loader2, Mail, Trash2, UserPlus, Users as UsersIcon } from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import { listMembers, inviteMember, updateMemberRole, removeMember, ApiError, type Member } from "../services/api";
import { formatDateTime, getInitials } from "../utils";
import { toast } from "../stores/toast";

const ROLE_OPTIONS = ["owner", "admin", "member", "viewer"] as const;

function StatusBadge({ status }: { status: Member["status"] }) {
  return status === "active" ? (
    <span className="badge bg-success-dim text-success text-[10px]">Active</span>
  ) : (
    <span className="badge bg-warning-dim text-warning text-[10px]">Invited</span>
  );
}

function MemberAvatar({ name }: { name: string }) {
  return (
    <div
      className="w-8 h-8 rounded-full bg-gradient-brand flex items-center justify-center flex-shrink-0"
      aria-hidden="true"
    >
      <span className="font-semibold text-app-bg text-[11px]">{getInitials(name)}</span>
    </div>
  );
}

function apiErrorMessage(err: unknown, fallback: string): { title: string; description: string } {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return { title: "Can't complete this change", description: "Every organization must keep at least one owner." };
    }
    if (err.status === 403) {
      return { title: "Not allowed", description: "You don't have permission to do that." };
    }
    if (err.status === 422) {
      return { title: "Invalid request", description: err.message };
    }
  }
  return { title: "Something went wrong", description: fallback };
}

export default function Users() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const currentEmail = useAuthStore((s) => s.user?.email);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<(typeof ROLE_OPTIONS)[number]>("member");
  const [roleUpdatingId, setRoleUpdatingId] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);

  const membersQuery = useQuery({
    queryKey: ["members", organizationId],
    queryFn: () => listMembers(organizationId!),
    enabled: !!organizationId,
  });

  const invite = useMutation({
    mutationFn: () => inviteMember(organizationId!, inviteEmail.trim(), inviteRole),
    onSuccess: (member) => {
      toast.success("Member added", `${member.email} was added as ${member.role}.`);
      setInviteEmail("");
      setInviteRole("member");
      void membersQuery.refetch();
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Already a member", "This email is already part of the organization.");
        return;
      }
      const { title, description } = apiErrorMessage(err, "Could not add this member. Please try again.");
      toast.error(title, description);
    },
  });

  const changeRole = useMutation({
    mutationFn: (vars: { membershipId: string; role: string }) =>
      updateMemberRole(organizationId!, vars.membershipId, vars.role),
    onMutate: (vars) => setRoleUpdatingId(vars.membershipId),
    onSuccess: (member) => {
      toast.success("Role updated", `${member.email} is now ${member.role}.`);
      void membersQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not update this role. Please try again.");
      toast.error(title, description);
    },
    onSettled: () => setRoleUpdatingId(null),
  });

  const remove = useMutation({
    mutationFn: (membershipId: string) => removeMember(organizationId!, membershipId),
    onSuccess: () => {
      toast.success("Member removed");
      setRemoveTarget(null);
      void membersQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not remove this member. Please try again.");
      toast.error(title, description);
    },
  });

  const members = membersQuery.data?.members ?? [];

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Users"
        description="Manage who has access to this organization and what they can do."
      />

      <Section title="Add a member" description="Adds them directly — no email is sent yet, so share the login link separately." icon={UserPlus}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!inviteEmail.trim()) return;
            invite.mutate();
          }}
          className="p-5 pt-0 flex flex-col sm:flex-row sm:items-end gap-3"
        >
          <div className="flex-1 min-w-0">
            <label htmlFor="invite-email" className="text-xs text-tx-muted block mb-1.5">Email</label>
            <div className="relative">
              <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
              <input
                id="invite-email"
                type="email"
                required
                placeholder="teammate@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="w-full bg-app-bg border border-border-subtle rounded-lg pl-9 pr-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
              />
            </div>
          </div>
          <div className="sm:w-40">
            <label htmlFor="invite-role" className="text-xs text-tx-muted block mb-1.5">Role</label>
            <select
              id="invite-role"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as (typeof ROLE_OPTIONS)[number])}
              className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary capitalize focus:outline-none focus:border-brand"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r} className="capitalize">{r}</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={invite.isPending || !inviteEmail.trim()}
            className="btn-primary h-9 text-xs px-4 sm:flex-shrink-0"
          >
            {invite.isPending ? <Loader2 size={13} className="animate-spin" /> : <UserPlus size={13} />}
            Add member
          </button>
        </form>
      </Section>

      <Section title="Members" description={`${members.length} ${members.length === 1 ? "person has" : "people have"} access`} icon={UsersIcon}>
        {membersQuery.isLoading ? (
          <div className="p-5 pt-0 space-y-2">
            {Array.from({ length: 3 }, (_, i) => <div key={i} className="h-14 skeleton rounded-lg" />)}
          </div>
        ) : membersQuery.isError ? (
          <EmptyState
            type="error"
            title="Couldn't load members"
            description="Something went wrong while fetching the member list."
          />
        ) : members.length === 0 ? (
          <EmptyState
            icon={UsersIcon}
            title="No members yet"
            description="Add a teammate above to get started."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-tx-muted">
                  <th className="px-5 py-3 font-medium">Member</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Added</th>
                  <th className="px-5 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m, i) => {
                  const isSelf = !!currentEmail && m.email.toLowerCase() === currentEmail.toLowerCase();
                  const isUpdating = roleUpdatingId === m.id;
                  return (
                    <motion.tr
                      key={m.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.03 }}
                      className="border-b border-border-subtle last:border-0 hover:bg-app-muted/40 transition-colors duration-fast"
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <MemberAvatar name={m.display_name || m.email} />
                          <div className="min-w-0">
                            <p className="text-tx-primary font-medium truncate">
                              {m.display_name || m.email}
                              {isSelf && <span className="text-tx-muted font-normal"> (you)</span>}
                            </p>
                            {m.display_name && <p className="text-xs text-tx-muted truncate">{m.email}</p>}
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <select
                          value={m.role}
                          disabled={isUpdating}
                          onChange={(e) => changeRole.mutate({ membershipId: m.id, role: e.target.value })}
                          className="bg-app-bg border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-tx-primary capitalize focus:outline-none focus:border-brand disabled:opacity-50"
                          aria-label={`Change role for ${m.email}`}
                        >
                          {ROLE_OPTIONS.map((r) => (
                            <option key={r} value={r} className="capitalize">{r}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-5 py-3"><StatusBadge status={m.status} /></td>
                      <td className="px-5 py-3 text-xs text-tx-muted whitespace-nowrap">{formatDateTime(m.created_at)}</td>
                      <td className="px-5 py-3 text-right">
                        <button
                          onClick={() => setRemoveTarget(m)}
                          className="btn-ghost h-8 w-8 !p-0 text-tx-muted hover:text-danger inline-flex items-center justify-center"
                          aria-label={`Remove ${m.email}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <ConfirmDialog
        open={!!removeTarget}
        title={removeTarget ? `Remove ${removeTarget.display_name || removeTarget.email}?` : ""}
        description="They will immediately lose access to this organization. This can't be undone."
        confirmLabel="Remove"
        loading={remove.isPending}
        onConfirm={() => removeTarget && remove.mutate(removeTarget.id)}
        onCancel={() => setRemoveTarget(null)}
      />
    </div>
  );
}
