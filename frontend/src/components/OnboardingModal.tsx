import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, BarChart3, Boxes, Check, FolderKanban, Sparkles } from "lucide-react";
import { CostorahMark } from "./CostorahLogo";
import { THEMES, useThemeStore } from "../stores/theme";
import { useOnboardingStore } from "../stores/onboarding";
import { useAuthStore } from "../stores/auth";
import { cn } from "../utils";

const TOUR_ITEMS = [
  { icon: Boxes, label: "Providers", desc: "See cost and usage across every connected AI provider in one place." },
  { icon: BarChart3, label: "Analytics", desc: "Break down spend trends and evaluate model-level cost efficiency." },
  { icon: FolderKanban, label: "Projects", desc: "Track budget utilization and catch overruns before they happen." },
];

const STEP_COUNT = 3;

export default function OnboardingModal() {
  const completed = useOnboardingStore((s) => s.completed);
  const complete = useOnboardingStore((s) => s.complete);
  const { user } = useAuthStore();
  const { theme, setTheme } = useThemeStore();
  const [step, setStep] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Move focus into the dialog on open; Escape skips the tour.
  useEffect(() => {
    if (completed) return undefined;
    dialogRef.current?.focus();
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") complete();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [completed, complete]);

  if (completed) return null;

  const firstName = user?.display_name?.split(" ")[0] ?? "there";

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[150] flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
          className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          aria-hidden="true"
        />

        <motion.div
          ref={dialogRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label="Welcome to Costorah"
          initial={{ opacity: 0, y: 16, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="relative w-full max-w-md glass-panel shadow-glow-brand-lg p-8 overflow-hidden"
        >
          {/* Step indicator */}
          <div className="flex items-center gap-1.5 mb-6" aria-hidden="true">
            {Array.from({ length: STEP_COUNT }, (_, i) => (
              <div
                key={i}
                className={cn(
                  "h-1 flex-1 rounded-full transition-colors duration-base",
                  i <= step ? "bg-brand" : "bg-app-muted",
                )}
              />
            ))}
          </div>

          <AnimatePresence mode="wait">
            {step === 0 && (
              <motion.div
                key="welcome"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <div className="relative w-14 h-14 mb-5">
                  <div className="absolute inset-0 bg-brand/25 blur-xl rounded-full animate-glow-pulse" />
                  <CostorahMark className="w-14 h-14 relative" />
                </div>
                <h2 className="font-display text-xl font-bold text-tx-primary mb-2">
                  Welcome, {firstName}
                </h2>
                <p className="text-sm text-tx-secondary leading-relaxed">
                  Costorah brings every AI provider, project, and dollar of spend into one
                  dashboard — with anomaly alerts before they hit your budget. Let&apos;s get
                  you set up.
                </p>
              </motion.div>
            )}

            {step === 1 && (
              <motion.div
                key="theme"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <div className="w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center mb-5">
                  <Sparkles size={24} className="text-brand" />
                </div>
                <h2 className="font-display text-xl font-bold text-tx-primary mb-2">Pick your look</h2>
                <p className="text-sm text-tx-secondary leading-relaxed mb-5">
                  Switch anytime from the top bar. Here&apos;s a preview.
                </p>
                <div className="space-y-2">
                  {THEMES.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setTheme(t.id)}
                      className={cn(
                        "w-full flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition-colors duration-fast",
                        theme === t.id
                          ? "border-brand bg-brand-subtle"
                          : "border-border-subtle hover:border-border hover:bg-app-hover",
                      )}
                    >
                      <div>
                        <p className="text-sm font-medium text-tx-primary">{t.label}</p>
                        <p className="text-xs text-tx-muted">{t.description}</p>
                      </div>
                      {theme === t.id && <Check size={16} className="text-brand flex-shrink-0" />}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div
                key="tour"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <h2 className="font-display text-xl font-bold text-tx-primary mb-2">Where to start</h2>
                <p className="text-sm text-tx-secondary leading-relaxed mb-5">
                  A quick tour of the essentials.
                </p>
                <div className="space-y-3">
                  {TOUR_ITEMS.map((item) => (
                    <div key={item.label} className="flex items-start gap-3">
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
              </motion.div>
            )}
          </AnimatePresence>

          <div className="flex items-center justify-between mt-8">
            <button
              onClick={complete}
              className="text-xs font-medium text-tx-muted hover:text-tx-secondary transition-colors duration-fast"
            >
              Skip
            </button>
            <button
              onClick={() => (step < STEP_COUNT - 1 ? setStep((s) => s + 1) : complete())}
              className="btn-primary h-10 px-5 text-sm"
            >
              {step < STEP_COUNT - 1 ? "Continue" : "Go to dashboard"}
              <ArrowRight size={15} />
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
