import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2, Lock, ArrowLeft, CheckCircle2, Eye, EyeOff } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { resetPassword, ApiError } from "../services/api";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && password !== confirm;
  const tooShort = password.length > 0 && password.length < 8;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (password.length < 8 || password !== confirm) return;
    setError(null);
    setLoading(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError("This reset link is invalid or has expired. Request a new one below.");
      } else {
        setError("Unable to reach the server. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <AuthShell>
        <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Invalid reset link</h1>
        <p className="text-sm text-tx-muted leading-relaxed mb-6">
          This page needs the reset token from your email. Follow the link in the
          message, or request a new one.
        </p>
        <Link to="/forgot-password" className="btn-primary h-10 text-sm inline-flex px-4">
          Request a new link
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      {done ? (
        <div className="text-center py-2">
          <div className="w-12 h-12 rounded-2xl bg-success-dim flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 size={22} className="text-success" />
          </div>
          <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Password updated</h1>
          <p className="text-sm text-tx-muted leading-relaxed mb-6">
            Your password has been reset and all other sessions were signed out.
          </p>
          <Link to="/login" className="btn-primary h-10 text-sm inline-flex px-4">
            Sign in
          </Link>
        </div>
      ) : (
        <>
          <h1 className="font-display text-lg font-bold text-tx-primary mb-1">Choose a new password</h1>
          <p className="text-sm text-tx-muted mb-6">Minimum 8 characters.</p>

          <form onSubmit={(e) => { void handleSubmit(e); }} className="space-y-4">
            <div>
              <label htmlFor="new-password" className="block text-xs font-medium text-tx-secondary mb-2">
                New password
              </label>
              <div className="relative group">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tx-muted transition-colors duration-fast group-focus-within:text-brand" />
                <input
                  id="new-password"
                  type={show ? "text" : "password"}
                  autoComplete="new-password"
                  required
                  autoFocus
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  disabled={loading}
                  aria-invalid={tooShort}
                  className="w-full h-11 pl-11 pr-11 text-sm bg-app-bg/60 border border-border-subtle rounded-xl
                             text-tx-primary placeholder:text-tx-muted
                             focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand/60
                             transition-all duration-fast disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => setShow((v) => !v)}
                  aria-label={show ? "Hide password" : "Show password"}
                  className="absolute right-0 top-0 h-11 w-11 flex items-center justify-center text-tx-muted hover:text-tx-secondary transition-colors duration-fast"
                >
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {tooShort && <p className="text-xs text-danger mt-1.5">Must be at least 8 characters.</p>}
            </div>

            <div>
              <label htmlFor="confirm-password" className="block text-xs font-medium text-tx-secondary mb-2">
                Confirm password
              </label>
              <div className="relative group">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tx-muted transition-colors duration-fast group-focus-within:text-brand" />
                <input
                  id="confirm-password"
                  type={show ? "text" : "password"}
                  autoComplete="new-password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  disabled={loading}
                  aria-invalid={mismatch}
                  className="w-full h-11 pl-11 pr-4 text-sm bg-app-bg/60 border border-border-subtle rounded-xl
                             text-tx-primary placeholder:text-tx-muted
                             focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand/60
                             transition-all duration-fast disabled:opacity-50"
                />
              </div>
              {mismatch && <p className="text-xs text-danger mt-1.5">Passwords don&apos;t match.</p>}
            </div>

            {error && (
              <div role="alert" className="text-xs text-danger bg-danger-dim border border-danger/20 rounded-xl p-3">
                {error}{" "}
                <Link to="/forgot-password" className="underline hover:text-danger-light">
                  Request a new link
                </Link>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || password.length < 8 || password !== confirm}
              className="btn-primary w-full h-11 text-sm"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              {loading ? "Updating…" : "Update password"}
            </button>
          </form>

          <Link
            to="/login"
            className="mt-6 inline-flex items-center gap-1.5 text-xs font-medium text-brand hover:text-brand-light transition-colors duration-fast"
          >
            <ArrowLeft size={13} /> Back to sign in
          </Link>
        </>
      )}
    </AuthShell>
  );
}
