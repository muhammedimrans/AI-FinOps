import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { Menu, X } from "lucide-react";

const links = [
  { to: "/features", label: "Features" },
  { to: "/pricing", label: "Pricing" },
  { to: "/security", label: "Security" },
  { to: "/developers", label: "Developers" },
  { to: "/docs", label: "Docs" },
  { to: "/blog", label: "Blog" },
  { to: "/about", label: "About" },
] as const;

export function SiteNav() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-[#05070A]/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2">
          <LogoMark />
          <span className="font-display text-lg font-semibold tracking-tight">Costorah</span>
        </Link>

        <nav className="hidden items-center gap-8 lg:flex">
          {links.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              activeProps={{ className: "text-foreground" }}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          <Link
            to="/login"
            className="rounded-full px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            Log in
          </Link>
          <Link
            to="/signup"
            className="rounded-full bg-gradient-brand px-4 py-2 text-sm font-medium text-primary-foreground transition-transform hover:scale-[1.02]"
          >
            Start free
          </Link>
        </div>

        <button
          className="rounded-md p-2 lg:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="border-t border-white/5 bg-[#05070A] px-6 py-4 lg:hidden">
          <div className="flex flex-col gap-3">
            {links.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                onClick={() => setOpen(false)}
                className="text-sm text-muted-foreground"
              >
                {l.label}
              </Link>
            ))}
            <div className="mt-3 flex gap-2">
              <Link
                to="/login"
                className="flex-1 rounded-full border border-white/10 px-4 py-2 text-center text-sm"
                onClick={() => setOpen(false)}
              >
                Log in
              </Link>
              <Link
                to="/signup"
                className="flex-1 rounded-full bg-gradient-brand px-4 py-2 text-center text-sm font-medium text-primary-foreground"
                onClick={() => setOpen(false)}
              >
                Start free
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#14D9D3" />
          <stop offset="100%" stopColor="#7AF7E8" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="url(#lg)" opacity="0.15" />
      <path
        d="M9 20 L14 12 L18 17 L23 10"
        stroke="url(#lg)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="23" cy="10" r="1.8" fill="#7AF7E8" />
    </svg>
  );
}
