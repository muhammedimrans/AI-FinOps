import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Loader2, AlertCircle, Eye, EyeOff, TrendingUp, Sparkles, Layers } from "lucide-react";
import { login, getOrganizations } from "../lib/api";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";
import CostorahLogo, { CostorahMark } from "../components/CostorahLogo";

export default function Login() {
  const { isAuthenticated, setLogin } = useAuthStore();
  const { setOrganization } = useOrgStore();
  const { theme } = useUIStore();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [forgotNotice, setForgotNotice] = useState(false);

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
      setLogin(data.access_token, data.refresh_token, {
        id: data.user.id,
        email: data.user.email,
        username: data.user.username,
        display_name: data.user.display_name,
        status: data.user.status,
        email_verified: data.user.email_verified,
      });
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
      if (err instanceof Error && err.message.includes("401")) {
        setError("Invalid email or password.");
      } else if (err instanceof Error && err.message.includes("403")) {
        setError("Your account has been disabled.");
      } else {
        setError("Unable to connect to the server. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={cn("min-h-screen w-full flex bg-app-bg", theme)}>
      {/* ── Left panel — brand illustration (hidden on mobile/tablet) ──────── */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden items-center justify-center p-12">
        <div className="absolute inset-0 bg-gradient-brand-radial" />
        <NetworkBackdrop />

        <div className="relative z-10 max-w-md w-full">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="flex items-center gap-3 mb-10"
          >
            <CostorahMark className="w-10 h-10" />
            <span className="text-lg font-bold tracking-[0.1em] text-tx-primary">COSTORAH</span>
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1, ease: "easeOut" }}
            className="text-h2 text-tx-primary mb-3 leading-tight"
          >
            Track, analyze, and optimize
            <br />
            your AI spend in real time.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.18, ease: "easeOut" }}
            className="text-sm text-tx-secondary mb-12 max-w-sm"
          >
            One dashboard for every provider, every project, every dollar —
            with anomaly alerts before they hit your budget.
          </motion.p>

          <FloatingMetricCards />
        </div>
      </div>

      {/* ── Right panel — auth form ─────────────────────────────────────────── */}
      <div className="flex flex-1 items-center justify-center p-4 sm:p-6 lg:p-12 relative">
        <div className="lg:hidden absolute inset-0 bg-gradient-brand-radial pointer-events-none" />

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="w-full max-w-sm relative z-10"
        >
          <div className="lg:hidden mb-8">
            <CostorahLogo />
          </div>

          <div className="glass-card border border-border-subtle p-6 sm:p-8 shadow-card">
            <h1 className="text-xl font-bold text-tx-primary mb-1">Welcome back</h1>
            <p className="text-sm text-tx-muted mb-6">Sign in to your account to continue</p>

            <form onSubmit={(e) => { void handleSubmit(e); }} className="space-y-4" noValidate>
              <div>
                <label htmlFor="email" className="block text-xs font-medium text-tx-secondary mb-1.5">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  aria-invalid={!!error}
                  className="w-full h-11 px-3.5 text-sm bg-app-bg border border-border-subtle rounded-lg
                             text-tx-primary placeholder:text-tx-muted
                             focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand/60
                             transition-colors duration-fast disabled:opacity-50"
                  disabled={loading}
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label htmlFor="password" className="block text-xs font-medium text-tx-secondary">
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={() => setForgotNotice(true)}
                    className="text-xs font-medium text-brand hover:text-brand-light transition-colors duration-fast"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    aria-invalid={!!error}
                    className="w-full h-11 px-3.5 pr-10 text-sm bg-app-bg border border-border-subtle rounded-lg
                               text-tx-primary placeholder:text-tx-muted
                               focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand/60
                               transition-colors duration-fast disabled:opacity-50"
                    disabled={loading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    disabled={loading}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-0 top-0 h-11 w-10 flex items-center justify-center
                               text-tx-muted hover:text-tx-secondary transition-colors duration-fast"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 rounded border-border-subtle bg-app-bg accent-brand
                             focus:outline-none focus:ring-2 focus:ring-brand/40"
                />
                <span className="text-xs text-tx-secondary">Remember me</span>
              </label>

              {forgotNotice && (
                <div
                  role="status"
                  className="flex items-start gap-2 p-3 rounded-lg bg-info-dim border border-info/20 animate-fade-in"
                >
                  <AlertCircle size={14} className="text-info mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-info">
                    Contact your administrator to reset your password.
                  </p>
                </div>
              )}

              {error && (
                <div
                  role="alert"
                  className="flex items-start gap-2 p-3 rounded-lg bg-danger-dim border border-danger/20 animate-fade-in"
                >
                  <AlertCircle size={14} className="text-danger mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-danger">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !email || !password}
                className="w-full h-11 rounded-lg bg-gradient-brand text-app-bg text-sm font-semibold
                           flex items-center justify-center gap-2 shadow-glow-brand
                           hover:brightness-110 active:brightness-95
                           transition-all duration-fast disabled:opacity-50 disabled:cursor-not-allowed
                           disabled:shadow-none"
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Signing in…
                  </>
                ) : (
                  "Sign in"
                )}
              </button>
            </form>
          </div>

          <p className="text-center text-xs text-tx-muted mt-4">
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
    { x: 60, y: 80 }, { x: 220, y: 40 }, { x: 340, y: 140 },
    { x: 120, y: 220 }, { x: 300, y: 280 }, { x: 40, y: 340 },
  ];
  const edges: [number, number][] = [[0, 1], [1, 2], [0, 3], [3, 4], [2, 4], [3, 5]];

  return (
    <svg
      className="absolute inset-0 w-full h-full opacity-40"
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
          stroke="#28E0C2"
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
          fill="#28E0C2"
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 3, delay: i * 0.3, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </svg>
  );
}

function FloatingMetricCards() {
  return (
    <div className="relative h-56">
      <motion.div
        className="absolute left-0 top-0 w-52 glass-card border border-border-subtle p-4"
        animate={{ y: [0, -8, 0] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
      >
        <div className="flex items-center gap-2 text-tx-muted text-[11px] font-medium uppercase tracking-wide mb-1.5">
          <TrendingUp size={12} className="text-brand" />
          Total Cost
        </div>
        <div className="text-xl font-bold text-tx-primary">$142,580.45</div>
        <div className="text-[11px] text-brand mt-0.5">+12.9% vs last 30d</div>
        <Sparkline />
      </motion.div>

      <motion.div
        className="absolute right-0 top-16 w-44 glass-card border border-border-subtle p-3.5"
        animate={{ y: [0, 10, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", delay: 0.6 }}
      >
        <div className="flex items-center gap-2 text-tx-muted text-[11px] font-medium uppercase tracking-wide mb-2">
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
              <span className={cn("w-1.5 h-1.5 rounded-full", p.color)} />
              <span className="text-[11px] text-tx-secondary flex-1">{p.name}</span>
              <span className="text-[11px] text-tx-muted">{p.pct}%</span>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div
        className="absolute left-10 bottom-0 w-40 glass-card border border-border-subtle px-3.5 py-2.5 flex items-center gap-2.5"
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut", delay: 1.1 }}
      >
        <div className="w-7 h-7 rounded-full bg-brand-subtle flex items-center justify-center flex-shrink-0">
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
    <svg viewBox="0 0 120 32" className="w-full h-8 mt-2" aria-hidden="true">
      <motion.path
        d="M0,24 L15,20 L30,22 L45,12 L60,16 L75,6 L90,10 L105,4 L120,8"
        fill="none"
        stroke="#28E0C2"
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
