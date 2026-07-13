import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Loader2, Mail, ArrowLeft, MailCheck } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { requestPasswordReset } from "../services/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await requestPasswordReset(email);
      // The backend intentionally answers identically whether or not the
      // account exists — mirror that neutrality here.
      setSent(true);
    } catch {
      setError("Unable to reach the server. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      {sent ? (
        <div className="text-center py-2">
          <div className="w-12 h-12 rounded-2xl bg-success-dim flex items-center justify-center mx-auto mb-4">
            <MailCheck size={22} className="text-success" />
          </div>
          <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Check your inbox</h1>
          <p className="text-sm text-tx-muted leading-relaxed mb-6">
            If an account exists for <span className="text-tx-secondary">{email}</span>, a
            reset link is on its way. The link expires in 1 hour.
          </p>
          <Link to="/login" className="btn-outline h-10 text-sm inline-flex px-4">
            <ArrowLeft size={14} /> Back to sign in
          </Link>
        </div>
      ) : (
        <>
          <h1 className="font-display text-lg font-bold text-tx-primary mb-1">Reset your password</h1>
          <p className="text-sm text-tx-muted mb-6">
            Enter your account email and we&apos;ll send you a reset link.
          </p>

          <form onSubmit={(e) => { void handleSubmit(e); }} className="flex flex-col gap-4">
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-tx-secondary mb-2">
                Email address
              </label>
              <div className="relative group">
                <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tx-muted transition-colors duration-fast group-focus-within:text-brand" />
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  disabled={loading}
                  className="w-full h-11 pl-11 pr-4 text-sm bg-app-bg/60 border border-border-subtle rounded-xl
                             text-tx-primary placeholder:text-tx-muted
                             focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand/60
                             transition-all duration-fast disabled:opacity-50"
                />
              </div>
            </div>

            {error && (
              <p role="alert" className="text-xs text-danger bg-danger-dim border border-danger/20 rounded-xl p-3">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !email}
              className="btn-primary w-full h-11 text-sm"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              {loading ? "Sending…" : "Send reset link"}
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
