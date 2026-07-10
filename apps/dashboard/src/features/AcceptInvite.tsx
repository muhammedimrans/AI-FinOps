import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, UserCheck, UserX, Users } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { useAuthStore } from "../stores/auth";
import { acceptInvitation, declineInvitation, ApiError } from "../services/api";

type Status =
  | { kind: "idle" }
  | { kind: "accepting" | "declining" }
  | { kind: "accepted"; organizationName: string; role: string }
  | { kind: "declined" }
  | { kind: "error"; message: string };

/**
 * Public accept/decline landing page for an invitation email link
 * (EP-24.6). Accept requires an authenticated session — an
 * unauthenticated visitor is offered a sign-in link that preserves this
 * page's URL (including the token) via Login.tsx's `redirect` query
 * param, so the invitation flow continues automatically once they're
 * signed in. Decline never requires authentication.
 */
export default function AcceptInvite() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function handleAccept() {
    setStatus({ kind: "accepting" });
    try {
      const result = await acceptInvitation(token);
      setStatus({ kind: "accepted", organizationName: result.organization_name, role: result.role });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 400 || err.status === 403)) {
        setStatus({ kind: "error", message: err.message || "This invitation is invalid or has expired." });
      } else {
        setStatus({ kind: "error", message: "Unable to reach the server. Please try again later." });
      }
    }
  }

  async function handleDecline() {
    setStatus({ kind: "declining" });
    try {
      await declineInvitation(token);
      setStatus({ kind: "declined" });
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setStatus({ kind: "error", message: "This invitation is invalid or has expired." });
      } else {
        setStatus({ kind: "error", message: "Unable to reach the server. Please try again later." });
      }
    }
  }

  if (!token) {
    return (
      <AuthShell>
        <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Invalid invitation link</h1>
        <p className="text-sm text-tx-muted leading-relaxed mb-6">
          This page needs the invitation token from your email. Follow the link in the message
          you received.
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
        {(status.kind === "idle" || status.kind === "accepting" || status.kind === "declining") && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-brand-subtle flex items-center justify-center mx-auto mb-4">
              <Users size={22} className="text-brand" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">You've been invited</h1>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">
              Accept this invitation to join the workspace, or decline if you weren't expecting it.
            </p>

            {isAuthenticated ? (
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => void handleAccept()}
                  disabled={status.kind === "accepting" || status.kind === "declining"}
                  className="btn-primary h-10 text-sm"
                >
                  {status.kind === "accepting" && <Loader2 size={16} className="animate-spin" />}
                  Accept invitation
                </button>
                <button
                  onClick={() => void handleDecline()}
                  disabled={status.kind === "accepting" || status.kind === "declining"}
                  className="btn-outline h-10 text-sm"
                >
                  {status.kind === "declining" && <Loader2 size={16} className="animate-spin" />}
                  Decline
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <Link
                  to={`/login?redirect=${encodeURIComponent(`/accept-invite?token=${token}`)}`}
                  className="btn-primary h-10 text-sm inline-flex items-center justify-center"
                >
                  Sign in to accept
                </Link>
                <button
                  onClick={() => void handleDecline()}
                  disabled={status.kind === "declining"}
                  className="btn-outline h-10 text-sm"
                >
                  {status.kind === "declining" && <Loader2 size={16} className="animate-spin" />}
                  Decline
                </button>
                <p className="text-xs text-tx-muted mt-2">
                  Don't have an account yet? Create one on{" "}
                  <a
                    href="https://costorah.com/signup"
                    className="text-brand hover:underline"
                  >
                    costorah.com
                  </a>
                  , then come back to this link to accept.
                </p>
              </div>
            )}
          </>
        )}

        {status.kind === "accepted" && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-success-dim flex items-center justify-center mx-auto mb-4">
              <UserCheck size={22} className="text-success" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">
              You've joined {status.organizationName}
            </h1>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">
              You're now a {status.role} of this workspace.
            </p>
            <button onClick={() => navigate("/users")} className="btn-primary h-10 text-sm">
              Go to Members
            </button>
          </>
        )}

        {status.kind === "declined" && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-app-muted flex items-center justify-center mx-auto mb-4">
              <UserX size={22} className="text-tx-muted" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Invitation declined</h1>
            <p className="text-sm text-tx-muted leading-relaxed mb-6">
              You won't be added to this workspace. No further action is needed.
            </p>
            <Link to="/login" className="btn-outline h-10 text-sm inline-flex px-4">
              Back to sign in
            </Link>
          </>
        )}

        {status.kind === "error" && (
          <>
            <div className="w-12 h-12 rounded-2xl bg-danger-dim flex items-center justify-center mx-auto mb-4">
              <UserX size={22} className="text-danger" />
            </div>
            <h1 className="font-display text-lg font-bold text-tx-primary mb-2">Something went wrong</h1>
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
