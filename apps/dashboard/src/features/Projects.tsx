import { useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  FolderOpen,
  TrendingUp,
  TrendingDown,
  FolderKanban,
  DollarSign,
  Wallet,
  AlertOctagon,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import BudgetBar from "../components/BudgetBar";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import MetricCard from "../components/MetricCard";
import ConfirmDialog from "../components/ConfirmDialog";
import { useProjects } from "../hooks/useDashboard";
import {
  listProjectsCrud,
  createProject,
  updateProject,
  deleteProject,
  ApiError,
  type ProjectRecord,
} from "../services/api";
import { formatCost, formatNumber, modelDisplayName, cn } from "../utils";
import { useUIStore } from "../stores/ui";
import { useOrgStore } from "../stores/org";
import { toast } from "../stores/toast";

const ENVIRONMENTS: ProjectRecord["environment"][] = ["development", "staging", "production"];

const ENV_BADGE: Record<ProjectRecord["environment"], string> = {
  development: "bg-app-muted text-tx-muted",
  staging: "bg-warning-dim text-warning",
  production: "bg-success-dim text-success",
};

function AddProjectForm({ organizationId, onDone }: { organizationId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState<ProjectRecord["environment"]>("production");

  const create = useMutation({
    mutationFn: () => createProject(organizationId, { name: name.trim(), environment }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects-crud", organizationId] });
      toast.success("Project created", `"${name.trim()}" is ready.`);
      onDone();
    },
    onError: (err: unknown) => {
      toast.error("Couldn't create project", err instanceof ApiError ? err.message : "Please try again.");
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim().length === 0) return;
        create.mutate();
      }}
      className="flex flex-col sm:flex-row gap-2 rounded-xl border border-border-subtle bg-app-muted p-3"
    >
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Project name"
        disabled={create.isPending}
        autoFocus
        className="flex-1 rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
      />
      <select
        value={environment}
        onChange={(e) => setEnvironment(e.target.value as ProjectRecord["environment"])}
        disabled={create.isPending}
        className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
      >
        {ENVIRONMENTS.map((env) => (
          <option key={env} value={env}>
            {env}
          </option>
        ))}
      </select>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={create.isPending || name.trim().length === 0}
          className="btn-primary h-9 px-4 text-xs disabled:opacity-60"
        >
          {create.isPending ? "Creating…" : "Create"}
        </button>
        <button type="button" onClick={onDone} className="btn-ghost h-9 px-3 text-xs">
          Cancel
        </button>
      </div>
    </form>
  );
}

function ProjectCrudRow({ organizationId, project }: { organizationId: string; project: ProjectRecord }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(project.name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["projects-crud", organizationId] });

  const rename = useMutation({
    mutationFn: () => updateProject(organizationId, project.id, { name: name.trim() }),
    onSuccess: () => {
      setEditing(false);
      void invalidate();
      toast.success("Project renamed");
    },
    onError: (err: unknown) => {
      toast.error("Couldn't rename project", err instanceof ApiError ? err.message : "Please try again.");
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteProject(organizationId, project.id),
    onSuccess: () => {
      void invalidate();
      toast.success("Project deleted");
    },
    onError: () => toast.error("Couldn't delete project"),
  });

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-border-subtle bg-app-muted p-3">
      <div className="min-w-0 flex-1">
        {editing ? (
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={rename.isPending}
            autoFocus
            className="w-full rounded-lg border border-border-subtle bg-app-bg px-2 py-1 text-sm text-tx-primary outline-none focus:border-brand"
          />
        ) : (
          <p className="text-sm text-tx-primary truncate">{project.name}</p>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className={cn("badge text-[10px]", ENV_BADGE[project.environment])}>{project.environment}</span>

        {editing ? (
          <>
            <button
              onClick={() => rename.mutate()}
              disabled={rename.isPending || name.trim().length === 0}
              className="btn-primary h-7 px-2 text-[11px] disabled:opacity-60"
            >
              Save
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setName(project.name);
              }}
              className="btn-ghost h-7 px-2 text-[11px]"
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)} className="text-tx-muted hover:text-tx-primary" aria-label="Rename project">
              <Pencil size={13} />
            </button>
            <button onClick={() => setConfirmingDelete(true)} className="text-tx-muted hover:text-danger" aria-label="Delete project">
              <Trash2 size={13} />
            </button>
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this project?"
        description={`"${project.name}" will be removed. This can't be undone.`}
        confirmLabel="Delete"
        loading={remove.isPending}
        onConfirm={() => remove.mutate(undefined, { onSuccess: () => setConfirmingDelete(false) })}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}

function ManageProjectsSection() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const [adding, setAdding] = useState(false);

  const projectsCrud = useQuery({
    queryKey: ["projects-crud", organizationId],
    queryFn: () => listProjectsCrud(organizationId!),
    enabled: !!organizationId,
  });

  const list = projectsCrud.data?.projects ?? [];

  return (
    <Section
      title="Manage projects"
      description="Create, rename, and delete projects — attribution units usage and provider connections can be scoped to."
      icon={FolderKanban}
      actions={
        !adding && (
          <button onClick={() => setAdding(true)} className="btn-primary h-8 px-3 text-xs inline-flex items-center gap-1.5">
            <Plus size={13} /> New project
          </button>
        )
      }
    >
      <div className="space-y-3">
        {adding && organizationId && (
          <AddProjectForm organizationId={organizationId} onDone={() => setAdding(false)} />
        )}

        {projectsCrud.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 2 }, (_, i) => <div key={i} className="h-14 skeleton rounded-xl" />)}
          </div>
        ) : list.length === 0 ? (
          <EmptyState
            icon={FolderKanban}
            title="No projects yet"
            description="Create a project to start attributing usage and provider connections to it."
            action={
              !adding && organizationId ? (
                <button onClick={() => setAdding(true)} className="btn-primary h-9 px-4 text-sm">
                  Create project
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="space-y-2">
            {list.map((p) => (
              <ProjectCrudRow key={p.id} organizationId={organizationId!} project={p} />
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function MiniTrendLine({ data, positive }: { data: string[]; positive: boolean }) {
  const nums = data.map(parseFloat);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const w = 56, h = 20;
  const step = w / (nums.length - 1);

  const points = nums
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");

  return (
    <svg width={w} height={h}>
      <polyline
        points={points}
        fill="none"
        stroke={positive ? "rgb(var(--color-success))" : "rgb(var(--color-danger))"}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.8}
      />
    </svg>
  );
}

export default function Projects() {
  const { currency } = useUIStore();
  const projects = useProjects();

  const list = projects.data?.projects ?? [];
  const overBudget = list.filter((p) => p.budget_utilization_pct > 100);
  const nearBudget = list.filter((p) => p.budget_utilization_pct >= 80 && p.budget_utilization_pct <= 100);

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader title="Projects" description="Track budget utilization and spend by project." />

      <ManageProjectsSection />

      {/* Alert banner */}
      {!projects.isLoading && (overBudget.length > 0 || nearBudget.length > 0) && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn(
            "rounded-card p-4 flex items-start gap-3 border",
            overBudget.length > 0
              ? "bg-danger-dim border-danger/30"
              : "bg-warning-dim border-warning/30",
          )}
        >
          <AlertTriangle
            size={16}
            className={overBudget.length > 0 ? "text-danger mt-0.5" : "text-warning mt-0.5"}
          />
          <div>
            <p className={cn("text-sm font-semibold", overBudget.length > 0 ? "text-danger" : "text-warning")}>
              {overBudget.length > 0
                ? `${overBudget.length} project${overBudget.length > 1 ? "s" : ""} over budget`
                : `${nearBudget.length} project${nearBudget.length > 1 ? "s" : ""} approaching budget limit`}
            </p>
            <p className="text-xs text-tx-secondary mt-0.5">
              {overBudget.length > 0
                ? overBudget.map((p) => p.project_name).join(", ") + " exceeded allocated budget."
                : nearBudget.map((p) => p.project_name).join(", ") + " are over 80% of budget."}
            </p>
          </div>
        </motion.div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <MetricCard
            label="Total Projects"
            value={list.length}
            type="number"
            subtitle="active"
            icon={FolderKanban}
            gradient="teal"
            loading={projects.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <MetricCard
            label="Total Spend"
            value={list.reduce((s, p) => s + parseFloat(p.total_cost), 0)}
            type="currency"
            currency={currency}
            subtitle="combined"
            icon={DollarSign}
            gradient="blue"
            loading={projects.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MetricCard
            label="Total Budget"
            value={list.reduce((s, p) => s + parseFloat(p.budget), 0)}
            type="currency"
            currency={currency}
            subtitle="allocated"
            icon={Wallet}
            gradient="emerald"
            loading={projects.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <MetricCard
            label="Over Budget"
            value={overBudget.length}
            type="number"
            subtitle={overBudget.length > 0 ? "needs attention" : "all in range"}
            icon={AlertOctagon}
            gradient={overBudget.length > 0 ? "amber" : "teal"}
            loading={projects.isLoading}
          />
        </motion.div>
      </div>

      {/* Project Cards Grid */}
      {projects.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-64 skeleton rounded-card" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No projects found"
          description="No projects with AI spend in the selected period."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {list.map((p, i) => {
            const isOver = p.budget_utilization_pct > 100;
            const isNear = p.budget_utilization_pct >= 80 && !isOver;
            const positive = p.cost_trend < 0;
            return (
              <motion.div
                key={p.project_id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                whileHover={{ y: -3, transition: { duration: 0.2, ease: "easeOut" } }}
                className={cn(
                  "glass-card rounded-card-lg border p-5 cursor-pointer transition-shadow duration-base hover:shadow-elevated",
                  isOver ? "border-danger/30" : isNear ? "border-warning/30" : "border-border-subtle",
                )}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-sm font-semibold text-tx-primary">{p.project_name}</h3>
                    <p className="text-xs text-tx-muted mt-0.5">{p.team} Team</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {p.cost_trend !== 0 && (
                      <span className={cn("flex items-center gap-0.5 text-xs font-medium", positive ? "text-success" : "text-danger")}>
                        {positive ? <TrendingDown size={11} /> : <TrendingUp size={11} />}
                        {Math.abs(p.cost_trend).toFixed(1)}%
                      </span>
                    )}
                    <MiniTrendLine data={p.trend_data} positive={positive} />
                  </div>
                </div>

                {/* Budget bar */}
                <div className="mb-4">
                  <BudgetBar
                    used={p.total_cost}
                    total={p.budget}
                    pct={p.budget_utilization_pct}
                    currency={currency}
                  />
                </div>

                {/* Stats */}
                <div className="flex items-center justify-between text-xs text-tx-muted mb-3">
                  <span>{formatNumber(p.request_count, true)} requests</span>
                  <span className="font-semibold text-tx-primary">{formatCost(p.total_cost, currency, true)}</span>
                </div>

                {/* Top models */}
                <div className="flex flex-wrap gap-1">
                  {p.top_models.slice(0, 2).map((m) => (
                    <span key={m} className="text-[10px] font-mono bg-app-muted text-tx-muted px-1.5 py-0.5 rounded">
                      {modelDisplayName(m)}
                    </span>
                  ))}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
