import { type FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, Loader2 } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { useAuthStore } from "../stores/auth";
import { setPassword, ApiError } from "../services/api";

/**
 * Mandatory "Set Password" step for a first-time Google-only account
 * (EP-24.6.1, Issue 1). `ProtectedRoute` redirects here whenever
 * `user.password_configured === false` and never lets the user past it
 * until a password has actually been set — reusing the exact same
 * "gate every protected route on one derived field, redirect once" pattern
 * EP-21.3 already established for the onboarding wizard (`onboarding_completed`).
 *
 * Not shown to accounts that already have a password (password-registered,
 * or a Google account that previously completed this step) — those never
 * see `password_configured: false` in the first place.
 */
export default function SetPassword() {
  const navigate = useNavigate();
  const { user, updateUser } = useAuthStore();
  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already-configured accounts landing here directly (bookmark, back
  // button) skip straight past — mirrors Onboarding.tsx's own "and never
  // show it again" half of ProtectedRoute's redirect-in rule.
  useEffect(() => {
    if (user?.password_configured === true) {
      navigate("/dashboard", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (user?.password_configured === true) {
    return null;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      await setPassword(password);
      updateUser({ password_configured: true });
      navigate("/onboarding", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Already configured (e.g. a second tab raced this one) — the
        // account is fine either way, just move on.
        updateUser({ password_configured: true });
        navigate("/onboarding", { replace: true });
      } else if (err instanceof ApiError) {
        setError(err.message || "Could not set your password. Please try again.");
      } else {
        setError("Could not reach the server. Check your connection and try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      <div className="text-center mb-6">
        <div className="w-12 h-12 rounded-2xl bg-brand-subtle flex items-center justify-center mx-auto mb-4">
          <KeyRound size={22} className="text-brand" />
        </div>
        <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Set a password</h1>
        <p className="text-sm text-tx-muted leading-relaxed">
          {user?.display_name ? `Welcome, ${user.display_name}. ` : ""}
          You signed up with Google — set a password so you can also sign in with your
          email and password, and to keep your account recoverable.
        </p>
      </div>

      <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-4">
        {error && (
          <p
            role="alert"
            className="rounded-lg border border-danger/30 bg-danger-dim px-3 py-2 text-sm text-danger"
          >
            {error}
          </p>
        )}
        <div>
          <label className="text-sm text-tx-muted" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            disabled={loading}
            value={password}
            onChange={(e) => setPasswordValue(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-border-subtle bg-app-muted px-3 py-2.5 text-sm outline-none focus:border-brand/50 disabled:opacity-60"
          />
        </div>
        <div>
          <label className="text-sm text-tx-muted" htmlFor="confirm">
            Confirm password
          </label>
          <input
            id="confirm"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            disabled={loading}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-border-subtle bg-app-muted px-3 py-2.5 text-sm outline-none focus:border-brand/50 disabled:opacity-60"
          />
        </div>
        <button type="submit" disabled={loading} className="btn-primary h-10 w-full text-sm">
          {loading && <Loader2 size={16} className="animate-spin" />}
          Set password &amp; continue
        </button>
      </form>
    </AuthShell>
  );
}
