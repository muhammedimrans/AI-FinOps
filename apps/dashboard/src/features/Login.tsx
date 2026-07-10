import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  AlertCircle,
  Eye,
  EyeOff,
  Mail,
  Lock,
  Check,
  TrendingUp,
  Sparkles,
  Layers,
  ArrowRight,
} from "lucide-react";
import { login, getOrganizations, googleOAuthStartUrl, ApiError } from "../services/api";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { cn } from "../utils";
import CostorahLogo, { CostorahMark } from "../components/CostorahLogo";
import AuroraBackground from "../components/AuroraBackground";
import ThemeSwitcher from "../components/ThemeSwitcher";
import GoogleGlyph from "../components/GoogleGlyph";

export default function Login() {
  const { isAuthenticated, setLogin } = useAuthStore();
  const { setOrganization } = useOrgStore();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Already authenticated — go straight to dashboard
  if (isAuthenticated()) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await login({ email, password });
      setLogin(
        data.access_token,
        data.refresh_token,
        {
          id: data.user.id,
          email: data.user.email,
          username: data.user.username,
          display_name: data.user.display_name,
          status: data.user.status,
          email_verified: data.user.email_verified,
        },
        rememberMe,
      );
      // Auto-select org when the user belongs to exactly one.
      // For multi-org or zero-org cases, OrgSelector handles it after redirect.
      try {
        const orgsData = await getOrganizations();
        if (orgsData.organizations.length === 1) {
          const only = orgsData.organizations[0]!;
          setOrganization(only.id, only.name);
        }
      } catch {
        // Non-fatal — OrgSelector will recover on the next render.
      }
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid email or password.");
      } else if (err instanceof ApiError && err.status === 403) {
        setError("Your account has been disabled.");
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Please wait a moment and try again.");
      } else {
        setError("Unable to connect to the server. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen w-full overflow-hidden bg-app-bg">
      {/* Full-bleed ambient background shared by both panels — Aurora alone
          is the single ambient motion source; it previously ran alongside a
          30-particle drift field plus the left panel's pulsing network graph
          and floating cards, which together read as visually overwhelming
          ("dizzy") rather than ambient. */}
      <AuroraBackground />
      <div className="absolute right-4 top-4 z-20">
        <ThemeSwitcher />
      </div>

      {/* ── Left panel — brand illustration (hidden on mobile/tablet) ──────── */}
      <div className="relative z-10 hidden items-center justify-center overflow-hidden p-12 lg:flex lg:w-1/2">
        <NetworkBackdrop />

        <div className="relative z-10 w-full max-w-md">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="mb-12 flex items-center gap-3"
          >
            <div className="relative">
              <div className="absolute inset-0 animate-glow-pulse rounded-full bg-brand/30 blur-xl" />
              <CostorahMark className="relative h-12 w-12" />
            </div>
            <span className="font-display text-xl font-bold tracking-[0.12em] text-tx-primary">
              COSTORAH
            </span>
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1, ease: "easeOut" }}
            className="mb-4 font-display text-h1 leading-[1.15] tracking-tight text-tx-primary"
          >
            Track, analyze, and{" "}
            <span className="bg-gradient-brand bg-clip-text text-transparent">optimize</span> your
            AI spend in real time.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.18, ease: "easeOut" }}
            className="mb-14 max-w-sm text-base leading-relaxed text-tx-secondary"
          >
            One dashboard for every provider, every project, every dollar — with anomaly alerts
            before they hit your budget.
          </motion.p>

          <FloatingMetricCards />
        </div>
      </div>

      {/* ── Right panel — auth form ─────────────────────────────────────────── */}
      <div className="relative z-10 flex flex-1 items-center justify-center p-4 sm:p-6 lg:p-12">
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="relative w-full max-w-[480px]"
        >
          {/* Ambient glow blob behind the card */}
          <div
            className="pointer-events-none absolute -inset-8 bg-gradient-brand-radial opacity-60 blur-3xl"
            aria-hidden="true"
          />

          <div className="relative mb-8 lg:hidden">
            <CostorahLogo />
          </div>

          <div className="glass-panel relative p-8 shadow-glow-brand-lg sm:p-11">
            <div className="mb-8 hidden items-center gap-2.5 lg:flex">
              <CostorahMark className="h-8 w-8" />
              <span className="font-display text-sm font-bold tracking-[0.12em] text-tx-primary">
                COSTORAH
              </span>
            </div>

            <h1 className="mb-2 font-display text-h3 font-bold text-tx-primary">Welcome back</h1>
            <p className="mb-8 text-sm text-tx-muted">Sign in to your account to continue</p>

            <a
              href={googleOAuthStartUrl()}
              className="mb-5 flex h-12 w-full items-center justify-center gap-2.5 rounded-xl border border-border-subtle bg-app-bg/60 text-sm font-medium text-tx-primary transition-colors duration-fast hover:bg-app-hover"
            >
              <GoogleGlyph className="h-4 w-4" />
              Continue with Google
            </a>
            <div className="mb-5 flex items-center gap-3 text-xs text-tx-muted">
              <span className="h-px flex-1 bg-border-subtle" />
              or continue with email
              <span className="h-px flex-1 bg-border-subtle" />
            </div>

            <form
              onSubmit={(e) => {
                void handleSubmit(e);
              }}
              className="space-y-5"
              noValidate
            >
              <div>
                <label htmlFor="email" className="mb-2 block text-xs font-medium text-tx-secondary">
                  Email address
                </label>
                <div className="group relative">
                  <Mail
                    size={16}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tx-muted transition-colors duration-fast group-focus-within:text-brand"
                  />
                  <input
                    id="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    aria-invalid={!!error}
                    className="h-12 w-full rounded-xl border border-border-subtle bg-app-bg/60 pl-11 pr-4 text-sm text-tx-primary transition-all duration-fast placeholder:text-tx-muted focus:border-brand/60 focus:outline-none focus:ring-2 focus:ring-brand/40 disabled:opacity-50"
                    disabled={loading}
                  />
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label htmlFor="password" className="block text-xs font-medium text-tx-secondary">
                    Password
                  </label>
                  <Link
                    to="/forgot-password"
                    className="text-xs font-medium text-brand transition-colors duration-fast hover:text-brand-light"
                  >
                    Forgot password?
                  </Link>
                </div>
                <div className="group relative">
                  <Lock
                    size={16}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tx-muted transition-colors duration-fast group-focus-within:text-brand"
                  />
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    aria-invalid={!!error}
                    className="h-12 w-full rounded-xl border border-border-subtle bg-app-bg/60 pl-11 pr-11 text-sm text-tx-primary transition-all duration-fast placeholder:text-tx-muted focus:border-brand/60 focus:outline-none focus:ring-2 focus:ring-brand/40 disabled:opacity-50"
                    disabled={loading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    disabled={loading}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-0 top-0 flex h-12 w-11 items-center justify-center text-tx-muted transition-colors duration-fast hover:text-tx-secondary"
                  >
                    <AnimatePresence mode="wait" initial={false}>
                      <motion.span
                        key={showPassword ? "hide" : "show"}
                        initial={{ opacity: 0, scale: 0.7 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.7 }}
                        transition={{ duration: 0.12 }}
                        className="flex"
                      >
                        {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </motion.span>
                    </AnimatePresence>
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <label className="group flex cursor-pointer select-none items-center gap-2.5">
                  <span className="relative flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="peer sr-only"
                    />
                    <span
                      className={cn(
                        "flex h-[18px] w-[18px] items-center justify-center rounded-md border transition-all duration-fast",
                        "peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40",
                        rememberMe
                          ? "border-transparent bg-gradient-brand"
                          : "border-border-subtle bg-app-bg/60 group-hover:border-border",
                      )}
                    >
                      <AnimatePresence>
                        {rememberMe && (
                          <motion.span
                            initial={{ scale: 0, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0, opacity: 0 }}
                            transition={{ duration: 0.15 }}
                          >
                            <Check size={12} strokeWidth={3} className="text-app-bg" />
                          </motion.span>
                        )}
                      </AnimatePresence>
                    </span>
                  </span>
                  <span className="text-xs text-tx-secondary">Remember me</span>
                </label>
              </div>

              <AnimatePresence mode="popLayout">
                {error && (
                  <motion.div
                    key="error"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto", x: [0, -6, 6, -6, 6, 0] }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.4 }}
                    className="overflow-hidden"
                  >
                    <div
                      role="alert"
                      className="flex items-start gap-2 rounded-xl border border-danger/20 bg-danger-dim p-3"
                    >
                      <AlertCircle size={14} className="mt-0.5 flex-shrink-0 text-danger" />
                      <p className="text-xs text-danger">{error}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <motion.button
                type="submit"
                disabled={loading || !email || !password}
                whileHover={!loading && email && password ? { scale: 1.01 } : {}}
                whileTap={!loading && email && password ? { scale: 0.98 } : {}}
                className="group flex h-12 w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-gradient-brand bg-[length:200%_auto] text-sm font-semibold text-app-bg shadow-glow-brand transition-all duration-slow hover:bg-[position:100%_0] active:brightness-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
              >
                <AnimatePresence mode="wait" initial={false}>
                  {loading ? (
                    <motion.span
                      key="loading"
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.15 }}
                      className="flex items-center gap-2"
                    >
                      <Loader2 size={16} className="animate-spin" />
                      Signing in…
                    </motion.span>
                  ) : (
                    <motion.span
                      key="idle"
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.15 }}
                      className="flex items-center gap-1.5"
                    >
                      Sign in
                      <ArrowRight
                        size={15}
                        className="transition-transform duration-fast group-hover:translate-x-0.5"
                      />
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            </form>
          </div>

          <p className="mt-6 text-center text-xs text-tx-muted">
            Contact your administrator to create an account.
          </p>
        </motion.div>
      </div>
    </div>
  );
}

// ── Illustration pieces (left panel) ──────────────────────────────────────────

function NetworkBackdrop() {
  const nodes = [
    { x: 60, y: 80 },
    { x: 220, y: 40 },
    { x: 340, y: 140 },
    { x: 120, y: 220 },
    { x: 300, y: 280 },
    { x: 40, y: 340 },
  ];
  const edges: [number, number][] = [
    [0, 1],
    [1, 2],
    [0, 3],
    [3, 4],
    [2, 4],
    [3, 5],
  ];

  return (
    <svg
      className="absolute inset-0 h-full w-full opacity-40"
      viewBox="0 0 400 400"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {edges.map(([a, b], i) => (
        <motion.line
          key={i}
          x1={nodes[a]!.x}
          y1={nodes[a]!.y}
          x2={nodes[b]!.x}
          y2={nodes[b]!.y}
          stroke="rgb(var(--color-brand))"
          strokeWidth="0.5"
          strokeOpacity="0.35"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.2, delay: i * 0.08, ease: "easeOut" }}
        />
      ))}
      {nodes.map((n, i) => (
        <motion.circle
          key={i}
          cx={n.x}
          cy={n.y}
          r="2.5"
          fill="rgb(var(--color-brand))"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.7 }}
          transition={{ duration: 0.6, delay: 0.8 + i * 0.1, ease: "easeOut" }}
        />
      ))}
    </svg>
  );
}

function FloatingMetricCards() {
  return (
    <div className="relative h-56">
      <motion.div className="glass-card absolute left-0 top-0 w-52 animate-float border border-border-subtle p-4 shadow-elevated">
        <div className="mb-1.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-tx-muted">
          <TrendingUp size={12} className="text-brand" />
          Total Cost
        </div>
        <div className="text-xl font-bold text-tx-primary">$142,580.45</div>
        <div className="mt-0.5 text-[11px] text-brand">+12.9% vs last 30d</div>
        <Sparkline />
      </motion.div>

      <motion.div
        className="glass-card absolute right-0 top-16 w-44 animate-float-slow border border-border-subtle p-3.5 shadow-elevated"
        style={{ animationDelay: "0.6s" }}
      >
        <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-tx-muted">
          <Layers size={12} className="text-brand" />
          Providers
        </div>
        <div className="space-y-1.5">
          {[
            { name: "OpenAI", pct: 48, color: "bg-openai" },
            { name: "Anthropic", pct: 24, color: "bg-anthropic" },
            { name: "Google", pct: 15, color: "bg-google" },
          ].map((p) => (
            <div key={p.name} className="flex items-center gap-2">
              <span className={cn("h-1.5 w-1.5 rounded-full", p.color)} />
              <span className="flex-1 text-[11px] text-tx-secondary">{p.name}</span>
              <span className="text-[11px] text-tx-muted">{p.pct}%</span>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div
        className="glass-card absolute bottom-0 left-10 flex w-40 animate-float items-center gap-2.5 border border-border-subtle px-3.5 py-2.5 shadow-elevated"
        style={{ animationDelay: "1.1s" }}
      >
        <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-brand-subtle">
          <Sparkles size={13} className="text-brand" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-tx-primary">Anomaly detected</div>
          <div className="text-[10px] text-tx-muted">2 min ago</div>
        </div>
      </motion.div>
    </div>
  );
}

function Sparkline() {
  return (
    <svg viewBox="0 0 120 32" className="mt-2 h-8 w-full" aria-hidden="true">
      <motion.path
        d="M0,24 L15,20 L30,22 L45,12 L60,16 L75,6 L90,10 L105,4 L120,8"
        fill="none"
        stroke="rgb(var(--color-brand))"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 1.2, delay: 0.4, ease: "easeOut" }}
      />
    </svg>
  );
}
