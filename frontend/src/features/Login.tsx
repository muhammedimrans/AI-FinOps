import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { DollarSign, Loader2, AlertCircle } from "lucide-react";
import { login, getOrganizations } from "../lib/api";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";

export default function Login() {
  const { isAuthenticated, setLogin } = useAuthStore();
  const { setOrganization } = useOrgStore();
  const { theme } = useUIStore();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    <div className={cn("min-h-screen flex items-center justify-center bg-app-bg p-4", theme)}>
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-9 h-9 rounded-xl bg-primary/20 flex items-center justify-center">
            <DollarSign size={18} className="text-primary-light" />
          </div>
          <span className="text-lg font-bold text-tx-primary tracking-tight">AI FinOps</span>
        </div>

        <div className="glass-card border border-border-subtle p-8">
          <h1 className="text-xl font-bold text-tx-primary mb-1">Welcome back</h1>
          <p className="text-sm text-tx-muted mb-6">Sign in to your account to continue</p>

          <form onSubmit={(e) => { void handleSubmit(e); }} className="space-y-4">
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
                className="w-full px-3 py-2 text-sm bg-app-bg border border-border-subtle rounded-lg
                           text-tx-primary placeholder:text-tx-muted
                           focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60
                           transition-colors duration-150 disabled:opacity-50"
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-tx-secondary mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3 py-2 text-sm bg-app-bg border border-border-subtle rounded-lg
                           text-tx-primary placeholder:text-tx-muted
                           focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60
                           transition-colors duration-150 disabled:opacity-50"
                disabled={loading}
              />
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-danger-dim border border-danger/20">
                <AlertCircle size={14} className="text-danger mt-0.5 flex-shrink-0" />
                <p className="text-xs text-danger">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !email || !password}
              className="w-full h-9 rounded-lg bg-primary hover:bg-primary/90 text-white text-sm font-medium
                         flex items-center justify-center gap-2
                         transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
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
  );
}
