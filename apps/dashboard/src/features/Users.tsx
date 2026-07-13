import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Mail,
  Trash2,
  UserPlus,
  Users as UsersIcon,
  Clock,
  RefreshCw,
  X,
  Crown,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import Dialog from "../components/Dialog";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import {
  listMembers,
  updateMemberRole,
  removeMember,
  listInvitations,
  createInvitation,
  resendInvitation,
  cancelInvitation,
  transferOwnership,
  ApiError,
  type Member,
  type InvitationRecord,
} from "../services/api";
import { formatDateTime, getInitials } from "../utils";
import { toast } from "../stores/toast";

const ROLE_OPTIONS = ["owner", "admin", "member", "viewer"] as const;
const INVITE_ROLE_OPTIONS = ["admin", "member", "viewer"] as const;

function StatusBadge({ status }: { status: Member["status"] }) {
  return status === "active" ? (
    <span className="badge bg-success-dim text-success text-[10px]">Active</span>
  ) : (
    <span className="badge bg-warning-dim text-warning text-[10px]">Invited</span>
  );
}

function InvitationStatusBadge({ status }: { status: InvitationRecord["status"] }) {
  if (status === "expired") {
    return <span className="badge bg-danger-dim text-danger text-[10px]">Expired</span>;
  }
  return <span className="badge bg-warning-dim text-warning text-[10px]">Pending</span>;
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
      return {
        title: "Can't complete this change",
        description: err.message || "Every organization must keep at least one owner.",
      };
    }
    if (err.status === 403) {
      return { title: "Not allowed", description: err.message || "You don't have permission to do that." };
    }
    if (err.status === 422) {
      return { title: "Invalid request", description: err.message };
    }
    if (err.status === 429) {
      return { title: "Too many invitations", description: err.message };
    }
  }
  return { title: "Something went wrong", description: fallback };
}

export default function Users() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const currentEmail = useAuthStore((s) => s.user?.email);
  const queryClient = useQueryClient();

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<(typeof INVITE_ROLE_OPTIONS)[number]>("member");
  const [roleUpdatingId, setRoleUpdatingId] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);
  const [cancelTarget, setCancelTarget] = useState<InvitationRecord | null>(null);
  const [transferTarget, setTransferTarget] = useState<Member | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);

  const membersQuery = useQuery({
    queryKey: ["members", organizationId],
    queryFn: () => listMembers(organizationId!),
    enabled: !!organizationId,
  });

  const invitationsQuery = useQuery({
    queryKey: ["invitations", organizationId],
    queryFn: () => listInvitations(organizationId!),
    enabled: !!organizationId,
  });

  const invite = useMutation({
    mutationFn: () => createInvitation(organizationId!, inviteEmail.trim(), inviteRole),
    onSuccess: (invitation) => {
      toast.success("Invitation sent", `An invitation was sent to ${invitation.email}.`);
      setInviteEmail("");
      setInviteRole("member");
      setInviteOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["invitations", organizationId] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.status === 409) {
        toast.error(
          "Can't send this invitation",
          err.message || "This email already has a pending invitation or is already a member.",
        );
        return;
      }
      const { title, description } = apiErrorMessage(err, "Could not send this invitation. Please try again.");
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

  const resend = useMutation({
    mutationFn: (invitationId: string) => resendInvitation(invitationId),
    onMutate: (invitationId) => setResendingId(invitationId),
    onSuccess: () => {
      toast.success("Invitation resent");
      void invitationsQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not resend this invitation. Please try again.");
      toast.error(title, description);
    },
    onSettled: () => setResendingId(null),
  });

  const cancel = useMutation({
    mutationFn: (invitationId: string) => cancelInvitation(invitationId),
    onSuccess: () => {
      toast.success("Invitation cancelled");
      setCancelTarget(null);
      void invitationsQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(err, "Could not cancel this invitation. Please try again.");
      toast.error(title, description);
    },
  });

  const transfer = useMutation({
    mutationFn: (membershipId: string) => transferOwnership(organizationId!, membershipId),
    onSuccess: (member) => {
      toast.success("Ownership transferred", `${member.email} is now the owner.`);
      setTransferTarget(null);
      void membersQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description } = apiErrorMessage(
        err,
        "Could not transfer ownership. Please try again.",
      );
      toast.error(title, description);
    },
  });

  const members = membersQuery.data?.members ?? [];
  const invitations = invitationsQuery.data?.invitations ?? [];
  const currentMember = members.find(
    (m) => !!currentEmail && m.email.toLowerCase() === currentEmail.toLowerCase(),
  );
  const isOwner = currentMember?.role === "owner";

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 sm:gap-6">
      <PageHeader
        title="Members"
        description="Invite teammates, manage roles, and control who has access to this organization."
        actions={
          <button onClick={() => setInviteOpen(true)} className="btn-primary h-9 text-xs px-4">
            <UserPlus size={13} />
            Invite member
          </button>
        }
      />

      <Section
        title="Pending invitations"
        description={
          invitations.length === 0
            ? "No outstanding invitations"
            : `${invitations.length} ${invitations.length === 1 ? "invitation" : "invitations"} awaiting a response`
        }
        icon={Clock}
      >
        {invitationsQuery.isLoading ? (
          <div className="p-5 pt-0 flex flex-col gap-2">
            {Array.from({ length: 2 }, (_, i) => (
              <div key={i} className="h-12 skeleton rounded-lg" />
            ))}
          </div>
        ) : invitations.length === 0 ? (
          <p className="px-5 pb-5 text-xs text-tx-muted">
            Every invitation you send will show up here until it's accepted, declined, or expires.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-tx-muted">
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Expires</th>
                  <th className="px-5 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv, i) => (
                  <motion.tr
                    key={inv.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.03 }}
                    className="border-b border-border-subtle last:border-0 hover:bg-app-muted/40 transition-colors duration-fast"
                  >
                    <td className="px-5 py-3">
                      <p className="text-tx-primary font-medium truncate">{inv.email}</p>
                      {inv.invited_by_email && (
                        <p className="text-xs text-tx-muted truncate">
                          Invited by {inv.invited_by_name || inv.invited_by_email}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-3 text-xs text-tx-secondary capitalize">{inv.role}</td>
                    <td className="px-5 py-3">
                      <InvitationStatusBadge status={inv.status} />
                    </td>
                    <td className="px-5 py-3 text-xs text-tx-muted whitespace-nowrap">
                      {formatDateTime(inv.expires_at)}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => resend.mutate(inv.id)}
                          disabled={resendingId === inv.id}
                          className="btn-ghost h-8 !px-2.5 text-xs text-tx-muted hover:text-tx-primary inline-flex items-center gap-1.5"
                          aria-label={`Resend invitation to ${inv.email}`}
                        >
                          {resendingId === inv.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <RefreshCw size={12} />
                          )}
                          Resend
                        </button>
                        <button
                          onClick={() => setCancelTarget(inv)}
                          className="icon-btn icon-btn-danger w-8 h-8"
                          aria-label={`Cancel invitation to ${inv.email}`}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Members" description={`${members.length} ${members.length === 1 ? "person has" : "people have"} access`} icon={UsersIcon}>
        {membersQuery.isLoading ? (
          <div className="p-5 pt-0 flex flex-col gap-2">
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
            description="Invite a teammate above to get started."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-tx-muted">
                  <th className="px-5 py-3 font-medium">Member</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Joined</th>
                  <th className="px-5 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m, i) => {
                  const isSelf = !!currentEmail && m.email.toLowerCase() === currentEmail.toLowerCase();
                  const isUpdating = roleUpdatingId === m.id;
                  const isTargetOwner = m.role === "owner";
                  // Owners can't demote themselves via this dropdown (backend
                  // rejects it too — transfer ownership is the sanctioned path).
                  const roleLocked = isSelf && isTargetOwner;
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
                          disabled={isUpdating || roleLocked}
                          title={roleLocked ? "Transfer ownership to change your own role" : undefined}
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
                        <div className="flex items-center justify-end gap-1.5">
                          {isOwner && !isTargetOwner && (
                            <button
                              onClick={() => setTransferTarget(m)}
                              className="btn-ghost h-8 !px-2.5 text-xs text-tx-muted hover:text-tx-primary inline-flex items-center gap-1.5"
                              aria-label={`Transfer ownership to ${m.email}`}
                            >
                              <Crown size={12} />
                              Make owner
                            </button>
                          )}
                          <button
                            onClick={() => setRemoveTarget(m)}
                            disabled={isSelf && isTargetOwner}
                            className="icon-btn icon-btn-danger w-8 h-8"
                            aria-label={`Remove ${m.email}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Dialog
        open={inviteOpen}
        title="Invite a member"
        onClose={() => (invite.isPending ? undefined : setInviteOpen(false))}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!inviteEmail.trim()) return;
            invite.mutate();
          }}
        >
          <h2 className="text-sm font-semibold text-tx-primary mb-1">Invite a member</h2>
          <p className="text-xs text-tx-muted mb-4">
            They'll receive an email with a link to join. Nothing is granted until they accept.
          </p>

          <div className="flex flex-col gap-4">
            <div>
              <label htmlFor="invite-email" className="text-xs text-tx-muted block mb-1.5">Email</label>
              <div className="relative">
                <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
                <input
                  id="invite-email"
                  type="email"
                  required
                  autoFocus
                  placeholder="teammate@company.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full bg-app-bg border border-border-subtle rounded-lg pl-9 pr-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
                />
              </div>
            </div>
            <div>
              <label htmlFor="invite-role" className="text-xs text-tx-muted block mb-1.5">Role</label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as (typeof INVITE_ROLE_OPTIONS)[number])}
                className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary capitalize focus:outline-none focus:border-brand"
              >
                {INVITE_ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r} className="capitalize">{r}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 mt-6">
            <button
              type="button"
              onClick={() => setInviteOpen(false)}
              disabled={invite.isPending}
              className="btn-outline h-9 text-xs px-3.5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={invite.isPending || !inviteEmail.trim()}
              className="btn-primary h-9 text-xs px-3.5"
            >
              {invite.isPending && <Loader2 size={13} className="animate-spin" />}
              Send invitation
            </button>
          </div>
        </form>
      </Dialog>

      <ConfirmDialog
        open={!!removeTarget}
        title={removeTarget ? `Remove ${removeTarget.display_name || removeTarget.email}?` : ""}
        description="They will immediately lose access to this organization. This can't be undone."
        confirmLabel="Remove"
        loading={remove.isPending}
        onConfirm={() => removeTarget && remove.mutate(removeTarget.id)}
        onCancel={() => setRemoveTarget(null)}
      />

      <ConfirmDialog
        open={!!cancelTarget}
        title={cancelTarget ? `Cancel invitation to ${cancelTarget.email}?` : ""}
        description="They will be notified their invitation was cancelled. No membership will be created."
        confirmLabel="Cancel invitation"
        loading={cancel.isPending}
        onConfirm={() => cancelTarget && cancel.mutate(cancelTarget.id)}
        onCancel={() => setCancelTarget(null)}
      />

      <ConfirmDialog
        open={!!transferTarget}
        title={transferTarget ? `Transfer ownership to ${transferTarget.display_name || transferTarget.email}?` : ""}
        description="You will become an Admin and lose owner-level permissions, including the ability to delete this organization. This can't be undone by yourself."
        confirmLabel="Transfer ownership"
        loading={transfer.isPending}
        onConfirm={() => transferTarget && transfer.mutate(transferTarget.id)}
        onCancel={() => setTransferTarget(null)}
      />
    </div>
  );
}
