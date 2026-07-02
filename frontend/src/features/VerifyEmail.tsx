import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2, MailCheck, MailX } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { verifyEmail, ApiError } from "../services/api";

type Status =
  | { kind: "verifying" }
  | { kind: "success" }
  | { kind: "already-verified" }
  | { kind: "error"; message: string };

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<Status>({ kind: "verifying" });
  const fired = useRef(false);

  useEffect(() => {
    if (!token || fired.current) return;
    fired.current = true; // tokens are single-use — never double-submit (StrictMode)
    verifyEmail(token)
      .then(() => setStatus({ kind: "success" }))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 409) {
          setStatus({ kind: "already-verified" });
        } else if (err instanceof ApiError && err.status === 400) {
          setStatus({ kind: "error", message: "This verification link is invalid or has expired." });
        } else {
          setStatus({ kind: "error", message: "Unable to reach the server. Please try again later." });
        }
      });
  }, [token]);

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

        {(status.kind === "success" || status.kind === "already-verified") && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-success-dim flex items-center justify-center mx-auto mb-4">
              <MailCheck size={22} className="text-success" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">
              {status.kind === "success" ? "Email verified" : "Already verified"}
            </h1>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">
              {status.kind === "success"
                ? "Your email address is confirmed — you're all set."
                : "This email address was already confirmed. You can sign in as usual."}
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
            <Link to="/login" className="btn-outline h-10 text-sm inline-flex px-4">
              Back to sign in
            </Link>
          </>
        )}
      </div>
    </AuthShell>
  );
}
