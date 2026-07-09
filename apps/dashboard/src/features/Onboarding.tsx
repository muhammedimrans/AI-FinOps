import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Sparkles, Wrench } from "lucide-react";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { useOnboardingStore } from "../stores/onboarding";
import { createApiKey, ApiError, type ApiKeyCreatedResponse } from "../services/api";
import { cn } from "../utils";
import CostorahLogo from "../components/CostorahLogo";

// EP-21.2: the 5-step wizard the registration flow redirects new users
// into (POST /v1/auth/register -> apps/website -> app.costorah.com/onboarding).
// Steps 2 and 3 (Connect Provider, Create Project) are honest placeholders,
// not broken links — ProviderConnection and Project have no CRUD API yet
// (see CLAUDE.md §7, EP-22/EP-23). Step 4 (Generate API Key) is real: it
// calls the same createApiKey() the ApiKeys.tsx page already uses.

const STEPS = ["Welcome", "Connect Provider", "Create Project", "API Key", "Dashboard"] as const;

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

function StepShell({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      key="step"
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -12 }}
      transition={{ duration: 0.2 }}
      className="glass-card rounded-card-lg border border-border-subtle p-8 sm:p-10 text-center max-w-lg w-full"
    >
      {children}
    </motion.div>
  );
}

function PendingFeaturePanel({
  title,
  description,
  requiredEndpoints,
  onNext,
  nextLabel = "Skip for now",
}: {
  title: string;
  description: string;
  requiredEndpoints: string[];
  onNext: () => void;
  nextLabel?: string;
}) {
  return (
    <StepShell>
      <div className="relative mx-auto mb-5 w-14 h-14">
        <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
        <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center">
          <Wrench size={24} className="text-brand" />
        </div>
      </div>
      <h2 className="text-lg font-semibold text-tx-primary mb-2">{title}</h2>
      <p className="text-sm text-tx-muted leading-relaxed">{description}</p>
      <div className="mt-5 text-left inline-block">
        <p className="text-[11px] font-semibold text-tx-muted uppercase tracking-wide mb-2">
          Backend endpoints required
        </p>
        <ul className="space-y-1.5">
          {requiredEndpoints.map((ep) => (
            <li key={ep}>
              <code className="text-xs font-mono bg-app-muted text-tx-secondary px-2 py-1 rounded-md">
                {ep}
              </code>
            </li>
          ))}
        </ul>
      </div>
      <button onClick={onNext} className="btn-primary mt-8 w-full">
        {nextLabel}
      </button>
    </StepShell>
  );
}

export default function Onboarding() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const organizationId = useOrgStore((s) => s.organizationId);
  const completeTour = useOnboardingStore((s) => s.complete);
  const [step, setStep] = useState(0);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreatedResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const createKey = useMutation({
    mutationFn: () =>
      createApiKey(organizationId!, {
        name: "Onboarding key",
        permissions: ["usage:read", "usage:write"],
        expiration: "never",
      }),
    onSuccess: (created) => setCreatedKey(created),
  });

  const firstName = user?.display_name?.split(" ")[0] ?? "there";
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));

  function finish() {
    completeTour(); // don't also show the feature-tour modal right after this
    navigate("/dashboard", { replace: true });
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-12 bg-app-bg">
      <CostorahLogo className="h-8 mb-8" />
      <StepDots current={step} />
      <AnimatePresence mode="wait">
        {step === 0 && (
          <StepShell key="welcome">
            <div className="relative mx-auto mb-5 w-14 h-14">
              <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
              <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center">
                <Sparkles size={24} className="text-brand" />
              </div>
            </div>
            <h1 className="text-xl font-semibold text-tx-primary mb-2">Welcome, {firstName}</h1>
            <p className="text-sm text-tx-muted leading-relaxed">
              Your personal workspace is ready. Let&apos;s get your AI cost data flowing in —
              this takes about a minute.
            </p>
            <button onClick={next} className="btn-primary mt-8 w-full">
              Get started
            </button>
          </StepShell>
        )}

        {step === 1 && (
          <PendingFeaturePanel
            title="Connect an AI provider"
            description="Persisted, customer-managed provider connections (OpenAI, Anthropic, etc.) aren't wired up yet — this is planned as EP-22. You can still send usage data via the Costorah SDK once you have an API key (next step)."
            requiredEndpoints={["POST /v1/organizations/{org_id}/provider-connections"]}
            onNext={next}
          />
        )}

        {step === 2 && (
          <PendingFeaturePanel
            title="Create your first project"
            description="Project creation isn't wired up yet — this is planned as EP-23. Usage you send via the SDK is still tracked at the organization level in the meantime."
            requiredEndpoints={["POST /v1/organizations/{org_id}/projects"]}
            onNext={next}
          />
        )}

        {step === 3 && (
          <StepShell key="apikey">
            <div className="relative mx-auto mb-5 w-14 h-14">
              <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
              <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center">
                <KeyRound size={24} className="text-brand" />
              </div>
            </div>
            <h2 className="text-lg font-semibold text-tx-primary mb-2">Generate an API key</h2>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">
              Use this key with the Costorah SDK to start sending usage data.
            </p>

            {!createdKey ? (
              <>
                {createKey.isError && (
                  <p className="mb-4 text-sm text-danger">
                    {createKey.error instanceof ApiError
                      ? createKey.error.message
                      : "Could not create a key. Please try again."}
                  </p>
                )}
                <button
                  onClick={() => createKey.mutate()}
                  disabled={createKey.isPending || !organizationId}
                  className="btn-primary w-full disabled:opacity-60"
                >
                  {createKey.isPending ? "Generating…" : "Generate API key"}
                </button>
                <button onClick={next} className="btn-ghost mt-3 w-full text-sm">
                  Skip for now
                </button>
              </>
            ) : (
              <>
                <div className="rounded-lg border border-border-subtle bg-app-muted p-3 flex items-center justify-between gap-3">
                  <code className="text-xs font-mono text-tx-primary truncate">
                    {createdKey.api_key}
                  </code>
                  <button
                    onClick={() => {
                      void navigator.clipboard.writeText(createdKey.api_key);
                      setCopied(true);
                    }}
                    className="shrink-0 text-tx-muted hover:text-tx-primary"
                    aria-label="Copy API key"
                  >
                    {copied ? <Check size={16} className="text-success" /> : <Copy size={16} />}
                  </button>
                </div>
                <p className="mt-3 text-xs text-tx-muted">
                  This is shown once — copy it now and store it securely.
                </p>
                <button onClick={next} className="btn-primary mt-6 w-full">
                  Continue
                </button>
              </>
            )}
          </StepShell>
        )}

        {step === 4 && (
          <StepShell key="done">
            <div className="relative mx-auto mb-5 w-14 h-14">
              <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
              <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center">
                <Check size={24} className="text-brand" />
              </div>
            </div>
            <h2 className="text-lg font-semibold text-tx-primary mb-2">You&apos;re all set</h2>
            <p className="text-sm text-tx-muted leading-relaxed">
              Your workspace is ready. Costs and usage will appear on your dashboard as soon as
              data starts coming in.
            </p>
            <button onClick={finish} className="btn-primary mt-8 w-full">
              Open dashboard
            </button>
          </StepShell>
        )}
      </AnimatePresence>
    </div>
  );
}
