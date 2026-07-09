import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Loader2, Plus, Trash2 } from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import Dialog from "../components/Dialog";
import { useOrgStore } from "../stores/org";
import {
  listApiKeys,
  createApiKey,
  revokeApiKey,
  listPermissions,
  ApiError,
  type ApiKey,
  type ApiKeyCreatedResponse,
  type ApiKeyExpiration,
} from "../services/api";
import { formatDateTime } from "../utils";
import { toast } from "../stores/toast";

const EXPIRATION_OPTIONS: { value: ApiKeyExpiration; label: string }[] = [
  { value: "never", label: "Never" },
  { value: "30d", label: "30 Days" },
  { value: "90d", label: "90 Days" },
];

function apiErrorMessage(err: unknown, fallback: string): { title: string; description: string } {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return { title: "Not allowed", description: "You don't have permission to do that." };
    }
    if (err.status === 422) {
      return { title: "Invalid request", description: err.message };
    }
  }
  return { title: "Something went wrong", description: fallback };
}

export default function ApiKeys() {
  const organizationId = useOrgStore((s) => s.organizationId);

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [expiration, setExpiration] = useState<ApiKeyExpiration>("never");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreatedResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ApiKey | null>(null);

  const keysQuery = useQuery({
    queryKey: ["api-keys", organizationId],
    queryFn: () => listApiKeys(organizationId!),
    enabled: !!organizationId,
  });

  const permissionsQuery = useQuery({
    queryKey: ["rbac-permissions"],
    queryFn: listPermissions,
    enabled: createOpen,
  });

  function resetForm() {
    setName("");
    setDescription("");
    setSelectedPermissions([]);
    setExpiration("never");
  }

  const create = useMutation({
    mutationFn: () =>
      createApiKey(organizationId!, {
        name: name.trim(),
        ...(description.trim() ? { description: description.trim() } : {}),
        permissions: selectedPermissions,
        expiration,
      }),
    onSuccess: (created) => {
      setCreateOpen(false);
      resetForm();
      setCreatedKey(created);
      void keysQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description: desc } = apiErrorMessage(err, "Could not create this key. Please try again.");
      toast.error(title, desc);
    },
  });

  const revoke = useMutation({
    mutationFn: (keyId: string) => revokeApiKey(organizationId!, keyId),
    onSuccess: () => {
      toast.success("API key revoked");
      setDeleteTarget(null);
      void keysQuery.refetch();
    },
    onError: (err: unknown) => {
      const { title, description: desc } = apiErrorMessage(err, "Could not revoke this key. Please try again.");
      toast.error(title, desc);
    },
  });

  function togglePermission(scope: string) {
    setSelectedPermissions((prev) =>
      prev.includes(scope) ? prev.filter((p) => p !== scope) : [...prev, scope],
    );
  }

  async function copyKey() {
    if (!createdKey) return;
    await navigator.clipboard?.writeText(createdKey.api_key);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  }

  const keys = keysQuery.data?.keys ?? [];

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="API Keys"
        description="Issue and revoke programmatic API keys for connecting external applications."
        actions={
          <button onClick={() => setCreateOpen(true)} className="btn-primary h-9 text-xs px-4">
            <Plus size={13} />
            Create API Key
          </button>
        }
      />

      <Section title="Keys" description={`${keys.length} active key${keys.length === 1 ? "" : "s"}`} icon={KeyRound}>
        {keysQuery.isLoading ? (
          <div className="p-5 pt-0 space-y-2">
            {Array.from({ length: 3 }, (_, i) => <div key={i} className="h-14 skeleton rounded-lg" />)}
          </div>
        ) : keysQuery.isError ? (
          <EmptyState
            type="error"
            title="Couldn't load API keys"
            description="Something went wrong while fetching your organization's API keys."
          />
        ) : keys.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="No API Keys created yet."
            description="Create your first API Key to connect external applications."
            action={
              <button onClick={() => setCreateOpen(true)} className="btn-primary h-9 text-xs px-4">
                <Plus size={13} />
                Create API Key
              </button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-tx-muted">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Prefix</th>
                  <th className="px-5 py-3 font-medium">Permissions</th>
                  <th className="px-5 py-3 font-medium">Created</th>
                  <th className="px-5 py-3 font-medium">Expires</th>
                  <th className="px-5 py-3 font-medium">Last Used</th>
                  <th className="px-5 py-3 font-medium text-right">Delete</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k, i) => (
                  <motion.tr
                    key={k.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.03 }}
                    className="border-b border-border-subtle last:border-0 hover:bg-app-muted/40 transition-colors duration-fast"
                  >
                    <td className="px-5 py-3 min-w-0">
                      <p className="text-tx-primary font-medium truncate">{k.name}</p>
                      {k.description && <p className="text-xs text-tx-muted truncate">{k.description}</p>}
                    </td>
                    <td className="px-5 py-3">
                      <code className="rounded-md bg-app-muted px-2 py-1 text-xs font-mono text-tx-secondary whitespace-nowrap">
                        {k.prefix}
                      </code>
                    </td>
                    <td className="px-5 py-3">
                      {k.permissions.length === 0 ? (
                        <span className="text-xs text-tx-muted">None</span>
                      ) : (
                        <span className="text-xs text-tx-secondary">
                          {k.permissions.length} scope{k.permissions.length === 1 ? "" : "s"}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-xs text-tx-muted whitespace-nowrap">{formatDateTime(k.created_at)}</td>
                    <td className="px-5 py-3 text-xs text-tx-muted whitespace-nowrap">
                      {k.expires_at ? formatDateTime(k.expires_at) : "Never"}
                    </td>
                    <td className="px-5 py-3 text-xs text-tx-muted whitespace-nowrap">
                      {k.last_used_at ? formatDateTime(k.last_used_at) : "Never used"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => setDeleteTarget(k)}
                        className="btn-ghost h-8 w-8 !p-0 text-tx-muted hover:text-danger inline-flex items-center justify-center"
                        aria-label={`Delete ${k.name}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Dialog
        open={createOpen}
        title="Create API Key"
        onClose={() => (create.isPending ? undefined : setCreateOpen(false))}
        maxWidthClassName="max-w-lg"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            create.mutate();
          }}
        >
          <h2 className="text-sm font-semibold text-tx-primary mb-4">Create API Key</h2>

          <div className="space-y-4">
            <div>
              <label htmlFor="key-name" className="text-xs text-tx-muted block mb-1.5">Name</label>
              <input
                id="key-name"
                required
                placeholder="Production ingestion"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand"
              />
            </div>

            <div>
              <label htmlFor="key-description" className="text-xs text-tx-muted block mb-1.5">Description</label>
              <textarea
                id="key-description"
                rows={2}
                placeholder="What will this key be used for?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary resize-none focus:outline-none focus:border-brand"
              />
            </div>

            <div>
              <span className="text-xs text-tx-muted block mb-1.5">Permissions</span>
              <div className="max-h-40 overflow-y-auto rounded-lg border border-border-subtle divide-y divide-border-subtle">
                {permissionsQuery.isLoading ? (
                  <div className="p-3 space-y-2">
                    {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-4 skeleton rounded" />)}
                  </div>
                ) : (
                  (permissionsQuery.data?.permissions ?? []).map((p) => (
                    <label
                      key={p.permission}
                      className="flex items-center gap-2.5 px-3 py-2 text-xs cursor-pointer hover:bg-app-muted/40"
                    >
                      <input
                        type="checkbox"
                        checked={selectedPermissions.includes(p.permission)}
                        onChange={() => togglePermission(p.permission)}
                        className="accent-brand"
                      />
                      <span className="text-tx-primary font-mono">{p.permission}</span>
                    </label>
                  ))
                )}
              </div>
              <p className="text-[11px] text-tx-muted mt-1">Leave empty to grant no scopes yet.</p>
            </div>

            <div>
              <span className="text-xs text-tx-muted block mb-1.5">Expiration</span>
              <div className="flex gap-2">
                {EXPIRATION_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setExpiration(opt.value)}
                    className={
                      expiration === opt.value
                        ? "flex-1 h-9 text-xs rounded-lg border border-brand bg-brand-subtle text-brand font-medium"
                        : "flex-1 h-9 text-xs rounded-lg border border-border-subtle text-tx-secondary hover:border-border"
                    }
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 mt-6">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              disabled={create.isPending}
              className="btn-outline h-9 text-xs px-3.5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={create.isPending || !name.trim()}
              className="btn-primary h-9 text-xs px-3.5"
            >
              {create.isPending && <Loader2 size={13} className="animate-spin" />}
              Create
            </button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={!!createdKey}
        title="API Key Created"
        onClose={() => setCreatedKey(null)}
        closeOnBackdrop={false}
        maxWidthClassName="max-w-lg"
      >
        <h2 className="text-sm font-semibold text-tx-primary mb-1">API Key Created</h2>
        <p className="text-xs text-danger font-medium mb-4">
          Copy this key now. It will never be shown again.
        </p>

        <div className="relative">
          <textarea
            readOnly
            rows={3}
            value={createdKey?.api_key ?? ""}
            onFocus={(e) => e.currentTarget.select()}
            className="w-full bg-app-muted border border-border-subtle rounded-lg px-3 py-2.5 pr-11 text-xs font-mono text-tx-primary resize-none focus:outline-none"
          />
          <button
            onClick={() => void copyKey()}
            aria-label="Copy API key"
            className="absolute top-2.5 right-2.5 btn-ghost h-7 w-7 !p-0 inline-flex items-center justify-center"
          >
            {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
          </button>
        </div>

        <div className="flex items-center justify-end mt-6">
          <button onClick={() => setCreatedKey(null)} className="btn-primary h-9 text-xs px-4">
            Close
          </button>
        </div>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete API Key?"
        description="This action cannot be undone. Any application using this key will immediately lose access."
        confirmLabel="Delete"
        loading={revoke.isPending}
        onConfirm={() => deleteTarget && revoke.mutate(deleteTarget.id)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
