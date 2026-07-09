import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  Bell,
  Check,
  FolderKanban,
  KeyRound,
  LayoutDashboard,
  Pencil,
  PlugZap,
  Sparkles,
  Wallet,
} from "lucide-react";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { useOnboardingStore } from "../stores/onboarding";
import {
  completeOnboarding,
  getOrganizations,
  updateOrganization,
  ApiError,
} from "../services/api";
import { PROVIDER_CATALOG } from "../lib/providerCatalog";
import { cn } from "../utils";
import { toast } from "../stores/toast";
import CostorahLogo from "../components/CostorahLogo";

// EP-21.3: the 5-step first-time onboarding wizard the registration flow
// (and any first login) redirects new users into — see
// ProtectedRoute.tsx for the "only show once" enforcement, which reads
// user.onboarding_completed from the backend (POST
// /v1/auth/onboarding/complete marks it done, called from Finish below).
//
// Step 3 (Choose Provider) intentionally does not build provider CRUD —
// ProviderConnection has no persistence API yet (EP-22). "Connect
// Provider" routes to the existing /connections page (live connectivity
// checks against server-side provider credentials), which is the closest
// real, working feature today.

const STEPS = ["Welcome", "Workspace", "Provider", "Tour", "Finish"] as const;

const ONBOARDING_PROVIDER_IDS = [
  "openai",
  "anthropic",
  "google",
  "openrouter",
  "azure",
  "xai",
  "ollama",
];

const TOUR_ITEMS = [
  {
    icon: LayoutDashboard,
    label: "Dashboard",
    desc: "Live KPIs, spend trends, and provider breakdowns at a glance.",
  },
  {
    icon: FolderKanban,
    label: "Projects",
    desc: "Group usage by product, team, or environment and track budgets.",
  },
  {
    icon: KeyRound,
    label: "API Keys",
    desc: "Generate scoped keys for the Costorah SDK to send usage data.",
  },
  {
    icon: Wallet,
    label: "Budgets",
    desc: "Set spending limits per provider or project before you get surprised.",
  },
  {
    icon: Bell,
    label: "Alerts",
    desc: "Real-time notifications when spend crosses a threshold or a provider errors.",
  },
  {
    icon: BarChart3,
    label: "Usage",
    desc: "Token-level detail across every connected model and provider.",
  },
  {
    icon: Sparkles,
    label: "Analytics",
    desc: "Forecasts and anomaly detection to catch cost spikes early.",
  },
] as const;

function StepDots({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8" aria-hidden="true">
      {STEPS.map((label, i) => (
        <div
          key={label}
          className={cn(
            "h-1.5 rounded-full transition-all duration-300",
            i === current ? "w-8 bg-brand" : i < current ? "w-1.5 bg-brand/50" : "w-1.5 bg-app-muted",
          )}
        />
      ))}
    </div>
  );
}

function StepShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <motion.div
      key="step"
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -12 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "glass-card rounded-card-lg border border-border-subtle p-6 sm:p-10 w-full",
        wide ? "max-w-2xl" : "max-w-lg text-center",
      )}
    >
      {children}
    </motion.div>
  );
}

function IconBadge({ icon: Icon }: { icon: typeof Sparkles }) {
  return (
    <div className="relative mx-auto mb-5 w-14 h-14">
      <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
      <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center">
        <Icon size={24} className="text-brand" />
      </div>
    </div>
  );
}

export default function Onboarding() {
  const navigate = useNavigate();
  const { user, updateUser } = useAuthStore();
  const organizationId = useOrgStore((s) => s.organizationId);
  const setOrganization = useOrgStore((s) => s.setOrganization);
  const completeTour = useOnboardingStore((s) => s.complete);
  const [step, setStep] = useState(0);

  const firstName = user?.display_name?.split(" ")[0] ?? "there";
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));

  const finishMutation = useMutation({
    mutationFn: completeOnboarding,
    onSuccess: (updated) => {
      updateUser({ onboarding_completed: updated.onboarding_completed });
      completeTour(); // don't also show the separate feature-tour modal right after this
    },
    onError: () => {
      // Non-fatal: the wizard already did its job locally. Worst case the
      // user sees onboarding once more on their next login.
      completeTour();
    },
  });

  function goToDashboard() {
    finishMutation.mutate(undefined, { onSettled: () => navigate("/dashboard", { replace: true }) });
  }

  function goToConnections() {
    finishMutation.mutate(undefined, { onSettled: () => navigate("/connections", { replace: true }) });
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-12 bg-app-bg">
      <CostorahLogo className="h-8 mb-8" />
      <StepDots current={step} />
      <AnimatePresence mode="wait">
        {step === 0 && <WelcomeStep key="welcome" firstName={firstName} onNext={next} />}
        {step === 1 && (
          <WorkspaceStep
            key="workspace"
            organizationId={organizationId}
            onNameSaved={(name) => organizationId && setOrganization(organizationId, name)}
            onNext={next}
          />
        )}
        {step === 2 && <ProviderStep key="provider" onSkip={next} onConnect={goToConnections} />}
        {step === 3 && <TourStep key="tour" onNext={next} />}
        {step === 4 && (
          <FinishStep
            key="finish"
            pending={finishMutation.isPending}
            onGoToDashboard={goToDashboard}
            onConnectProvider={goToConnections}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Step 1: Welcome ─────────────────────────────────────────────────────────

function WelcomeStep({ firstName, onNext }: { firstName: string; onNext: () => void }) {
  return (
    <StepShell>
      <IconBadge icon={Sparkles} />
      <h1 className="text-xl font-semibold text-tx-primary mb-2">
        Welcome to Costorah, {firstName}
      </h1>
      <p className="text-sm text-tx-muted leading-relaxed">
        Costorah brings every AI provider into one place, so you can:
      </p>
      <ul className="mt-4 space-y-2 text-left text-sm text-tx-secondary max-w-xs mx-auto">
        {[
          "Monitor AI costs across every provider in real time",
          "Optimize token usage and catch inefficient calls",
          "Control spending with budgets and hard limits",
          "Get alerts before a spike becomes a surprise bill",
          "Break down spend with detailed analytics",
        ].map((line) => (
          <li key={line} className="flex items-start gap-2">
            <Check size={15} className="text-brand mt-0.5 flex-shrink-0" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
      <button onClick={onNext} className="btn-primary mt-8 w-full">
        Get started
        <ArrowRight size={15} />
      </button>
    </StepShell>
  );
}

// ── Step 2: Workspace ────────────────────────────────────────────────────────

function WorkspaceStep({
  organizationId,
  onNameSaved,
  onNext,
}: {
  organizationId: string | null;
  onNameSaved: (name: string) => void;
  onNext: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });
  const current = data?.organizations.find((o) => o.id === organizationId);

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const displayName = name || current?.name || "";

  const saveMutation = useMutation({
    mutationFn: (newName: string) => updateOrganization(organizationId!, newName),
    onSuccess: (updated) => {
      setName(updated.name);
      setEditing(false);
      onNameSaved(updated.name);
      toast.success("Workspace renamed", `Now called "${updated.name}".`);
    },
    onError: (err) => {
      toast.error(
        "Couldn't rename workspace",
        err instanceof ApiError ? err.message : "Please try again.",
      );
    },
  });

  return (
    <StepShell>
      <IconBadge icon={LayoutDashboard} />
      <h2 className="text-lg font-semibold text-tx-primary mb-1">Personal Workspace</h2>
      <p className="text-sm text-tx-muted leading-relaxed mb-6">
        This is your private workspace — nobody else can see it unless you invite them.
      </p>

      <div className="text-left space-y-4">
        <div>
          <label
            htmlFor="workspace-name"
            className="text-xs font-semibold text-tx-muted uppercase tracking-wide"
          >
            Workspace name
          </label>
          {editing ? (
            <div className="mt-1.5 flex items-center gap-2">
              <input
                id="workspace-name"
                value={displayName}
                onChange={(e) => setName(e.target.value)}
                disabled={saveMutation.isPending}
                autoFocus
                className="flex-1 rounded-lg border border-border-subtle bg-app-muted px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
              />
              <button
                onClick={() => saveMutation.mutate(displayName.trim())}
                disabled={saveMutation.isPending || displayName.trim().length === 0}
                className="btn-primary h-9 px-3 text-xs disabled:opacity-60"
              >
                {saveMutation.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          ) : (
            <div className="mt-1.5 flex items-center justify-between gap-2 rounded-lg border border-border-subtle bg-app-muted px-3 py-2">
              <span className="text-sm text-tx-primary truncate">{displayName || "Loading…"}</span>
              <button
                onClick={() => {
                  setName(displayName);
                  setEditing(true);
                }}
                disabled={!current}
                className="shrink-0 text-tx-muted hover:text-tx-primary disabled:opacity-40"
                aria-label="Edit workspace name"
              >
                <Pencil size={14} />
              </button>
            </div>
          )}
        </div>

        <div>
          <label className="text-xs font-semibold text-tx-muted uppercase tracking-wide">
            Workspace slug
          </label>
          <div className="mt-1.5 rounded-lg border border-border-subtle bg-app-muted px-3 py-2">
            <code className="text-xs font-mono text-tx-muted">{current?.slug ?? "…"}</code>
          </div>
        </div>
      </div>

      <button onClick={onNext} className="btn-primary mt-8 w-full">
        Continue
        <ArrowRight size={15} />
      </button>
    </StepShell>
  );
}

// ── Step 3: Choose First Provider ────────────────────────────────────────────

function ProviderStep({ onSkip, onConnect }: { onSkip: () => void; onConnect: () => void }) {
  const providers = PROVIDER_CATALOG.filter((p) => ONBOARDING_PROVIDER_IDS.includes(p.id));

  return (
    <StepShell wide>
      <div className="text-center">
        <IconBadge icon={PlugZap} />
        <h2 className="text-lg font-semibold text-tx-primary mb-1">Choose your first provider</h2>
        <p className="text-sm text-tx-muted leading-relaxed mb-6 max-w-md mx-auto">
          Persisted, customer-managed provider connections are coming soon (EP-22). For now, use
          the SDK with an API key, or check live connectivity from Connections.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {providers.map((p) => (
          <div
            key={p.id}
            className="flex items-center gap-2.5 rounded-xl border border-border-subtle bg-app-muted px-3 py-3"
          >
            <span
              className="h-2.5 w-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: p.color }}
              aria-hidden="true"
            />
            <span className="text-sm text-tx-primary truncate">{p.name}</span>
          </div>
        ))}
      </div>

      <p className="mt-5 text-xs text-tx-muted text-center">You can connect providers later.</p>

      <div className="mt-6 flex flex-col sm:flex-row gap-3">
        <button onClick={onSkip} className="btn-ghost h-10 flex-1 text-sm">
          Skip for now
        </button>
        <button onClick={onConnect} className="btn-primary h-10 flex-1 text-sm">
          Connect provider
          <ArrowRight size={15} />
        </button>
      </div>
    </StepShell>
  );
}

// ── Step 4: Product Tour ─────────────────────────────────────────────────────

function TourStep({ onNext }: { onNext: () => void }) {
  return (
    <StepShell wide>
      <div className="text-center">
        <IconBadge icon={LayoutDashboard} />
        <h2 className="text-lg font-semibold text-tx-primary mb-1">A quick tour</h2>
        <p className="text-sm text-tx-muted leading-relaxed mb-6">
          Here&apos;s where everything lives once you&apos;re in.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 text-left">
        {TOUR_ITEMS.map((item) => (
          <div
            key={item.label}
            className="flex items-start gap-3 rounded-xl border border-border-subtle bg-app-muted p-3"
          >
            <div className="w-9 h-9 rounded-lg bg-brand-subtle flex items-center justify-center flex-shrink-0">
              <item.icon size={16} className="text-brand" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-tx-primary">{item.label}</p>
              <p className="text-xs text-tx-muted leading-relaxed">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <button onClick={onNext} className="btn-primary mt-8 w-full">
        Continue
        <ArrowRight size={15} />
      </button>
    </StepShell>
  );
}

// ── Step 5: Finish ───────────────────────────────────────────────────────────

function FinishStep({
  pending,
  onGoToDashboard,
  onConnectProvider,
}: {
  pending: boolean;
  onGoToDashboard: () => void;
  onConnectProvider: () => void;
}) {
  return (
    <StepShell>
      <IconBadge icon={Check} />
      <h2 className="text-lg font-semibold text-tx-primary mb-2">You&apos;re ready!</h2>
      <p className="text-sm text-tx-muted leading-relaxed">
        Your workspace is set up. Costs and usage will appear as soon as data starts coming in.
      </p>
      <div className="mt-8 flex flex-col sm:flex-row gap-3">
        <button
          onClick={onConnectProvider}
          disabled={pending}
          className="btn-ghost h-10 flex-1 text-sm disabled:opacity-60"
        >
          Connect provider
        </button>
        <button
          onClick={onGoToDashboard}
          disabled={pending}
          className="btn-primary h-10 flex-1 text-sm disabled:opacity-60"
        >
          {pending ? "One sec…" : "Go to dashboard"}
        </button>
      </div>
    </StepShell>
  );
}
