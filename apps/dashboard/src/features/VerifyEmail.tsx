import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2, Mail, MailCheck, MailX } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { verifyEmail, resendVerification, ApiError } from "../services/api";

type Status =
  | { kind: "verifying" }
  | { kind: "success" }
  | { kind: "error"; message: string };

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<Status>({ kind: "verifying" });
  const [resendEmail, setResendEmail] = useState("");
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">("idle");
  const fired = useRef(false);

  useEffect(() => {
    if (!token || fired.current) return;
    fired.current = true; // tokens are single-use — never double-submit (StrictMode)
    verifyEmail(token)
      .then(() => setStatus({ kind: "success" }))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 400) {
          setStatus({ kind: "error", message: "This verification link is invalid or has expired." });
        } else {
          setStatus({ kind: "error", message: "Unable to reach the server. Please try again later." });
        }
      });
  }, [token]);

  async function handleResend(e: React.FormEvent) {
    e.preventDefault();
    setResendState("sending");
    try {
      await resendVerification(resendEmail);
    } catch {
      // Anti-enumeration: the backend always returns the same generic
      // response; a network failure here is indistinguishable from
      // "sent" to the user, so we still show the confirmation state.
    } finally {
      setResendState("sent");
    }
  }

  if (!token) {
    return (
      <AuthShell>
        <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Invalid verification link</h1>
        <p className="text-sm text-tx-muted leading-relaxed mb-6">
          This page needs the verification token from your email. Follow the link
          in the message we sent you.
        </p>
        <Link to="/login" className="btn-outline h-10 text-sm inline-flex px-4">
          Back to sign in
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <div className="text-center py-2" aria-live="polite">
        {status.kind === "verifying" && (
          <>
            <Loader2 size={28} className="animate-spin text-brand mx-auto mb-4" />
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Verifying your email…</h1>
            <p className="text-sm text-tx-muted">This only takes a moment.</p>
          </>
        )}

        {status.kind === "success" && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-success-dim flex items-center justify-center mx-auto mb-4">
              <MailCheck size={22} className="text-success" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Email verified</h1>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">
              Your email address is confirmed — you're all set.
            </p>
            <Link to="/login" className="btn-primary h-10 text-sm inline-flex px-4">
              Sign in
            </Link>
          </>
        )}

        {status.kind === "error" && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-danger-dim flex items-center justify-center mx-auto mb-4">
              <MailX size={22} className="text-danger" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Verification failed</h1>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">{status.message}</p>

            {resendState === "sent" ? (
              <p className="text-xs text-tx-muted bg-app-muted border border-border-subtle rounded-xl p-3 mb-4">
                If that email has an account and isn't verified yet, a new link is on its way.
              </p>
            ) : (
              <form onSubmit={(e) => { void handleResend(e); }} className="text-left mb-4">
                <label htmlFor="resend-email" className="block text-xs font-medium text-tx-secondary mb-2">
                  Get a new verification link
                </label>
                <div className="relative group mb-3">
                  <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tx-muted transition-colors duration-fast group-focus-within:text-brand" />
                  <input
                    id="resend-email"
                    type="email"
                    autoComplete="email"
                    required
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    placeholder="you@example.com"
                    disabled={resendState === "sending"}
                    className="w-full h-11 pl-11 pr-4 text-sm bg-app-bg/60 border border-border-subtle rounded-xl
                               text-tx-primary placeholder:text-tx-muted
                               focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand/60
                               transition-all duration-fast disabled:opacity-50"
                  />
                </div>
                <button
                  type="submit"
                  disabled={resendState === "sending" || !resendEmail}
                  className="btn-primary w-full h-10 text-sm"
                >
                  {resendState === "sending" ? <Loader2 size={16} className="animate-spin" /> : null}
                  {resendState === "sending" ? "Sending…" : "Resend verification email"}
                </button>
              </form>
            )}

            <Link to="/login" className="btn-outline h-10 text-sm inline-flex px-4">
              Back to sign in
            </Link>
          </>
        )}
      </div>
    </AuthShell>
  );
}
