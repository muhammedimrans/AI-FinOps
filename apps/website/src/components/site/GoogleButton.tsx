import { googleOAuthStartUrl } from "@/lib/api";

/**
 * "Continue with Google" — EP-24.5. A plain anchor, not a button+fetch:
 * the flow is a full top-level navigation to the backend (see
 * googleOAuthStartUrl's own docstring), so there is no JS click handler
 * to wire up beyond the href itself.
 */
export function GoogleButton({ label = "Continue with Google" }: { label?: string }) {
  return (
    <a
      href={googleOAuthStartUrl()}
      className="flex w-full items-center justify-center gap-2.5 rounded-full border border-white/15 bg-white/[0.03] px-5 py-3 text-sm font-medium text-foreground transition-colors hover:bg-white/[0.06]"
    >
      <GoogleGlyph className="h-4 w-4" />
      {label}
    </a>
  );
}

function GoogleGlyph({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.87 2.69-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.35 0-4.34-1.58-5.05-3.71H.9v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.95 10.71A5.4 5.4 0 0 1 3.67 9c0-.6.1-1.18.28-1.71V4.96H.9A9 9 0 0 0 0 9c0 1.45.35 2.83.9 4.04l3.05-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.51.46 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .9 4.96l3.05 2.33C4.66 5.16 6.65 3.58 9 3.58Z"
      />
    </svg>
  );
}
