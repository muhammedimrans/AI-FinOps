import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";
import costorahMark from "../../assets/Costorah.png";

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
  const [elevated, setElevated] = useState(false);

  // Scroll-elevated header: transparent over the hero, condenses to a
  // blurred, hairline-bordered bar once the user scrolls. SSR-guarded.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onScroll = () => setElevated(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 transition-all duration-300 ${
        elevated
          ? "border-b border-white/[0.07] bg-[#060810]/80 backdrop-blur-xl"
          : "border-b border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-[80rem] items-center justify-between px-6">
        <Link to="/" className="group flex items-center gap-2.5">
          <span className="relative">
            <span className="absolute inset-0 -z-10 rounded-full bg-[#14D9D3]/40 opacity-0 blur-md transition-opacity duration-300 group-hover:opacity-100" />
            <LogoMark />
          </span>
          <span className="font-display text-[1.05rem] font-semibold tracking-tight">Costorah</span>
        </Link>

        <nav className="hidden items-center gap-1 lg:flex">
          {links.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="relative rounded-lg px-3 py-2 text-[0.8125rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
              activeProps={{ className: "text-foreground" }}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-1.5 lg:flex">
          <Link
            to="/login"
            className="rounded-full px-4 py-2 text-[0.8125rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            Log in
          </Link>
          <Link
            to="/signup"
            className="btn-brand group px-4 py-2 text-[0.8125rem] hover:scale-[1.02] hover:brightness-105 active:scale-[0.98]"
          >
            Start free
            <ArrowRight className="size-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </Link>
        </div>

        <button
          className="rounded-lg p-2 text-foreground/80 hover:text-foreground lg:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
          aria-expanded={open}
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>

      {open && (
        <div className="border-t border-white/5 bg-[#060810] px-6 py-5 lg:hidden">
          <div className="flex flex-col gap-1">
            {links.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                onClick={() => setOpen(false)}
                className="rounded-lg px-2 py-2.5 text-sm font-medium text-muted-foreground hover:bg-white/5 hover:text-foreground"
                activeProps={{ className: "text-foreground bg-white/5" }}
              >
                {l.label}
              </Link>
            ))}
            <div className="mt-4 flex gap-2">
              <Link
                to="/login"
                className="btn-ghost flex-1 px-4 py-2.5 text-center text-sm hover:bg-white/[0.06]"
                onClick={() => setOpen(false)}
              >
                Log in
              </Link>
              <Link
                to="/signup"
                className="btn-brand flex-1 px-4 py-2.5 text-center text-sm"
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

// EP-25.3/EP-25.3.1 — the official Costorah brand mark (src/assets/Costorah.png,
// provided by the product team), the same real asset apps/dashboard uses, not a
// hand-drawn approximation. Both apps rendering literally the same image is
// what "brand consistency" means here.
export function LogoMark({ className = "size-7" }: { className?: string }) {
  return (
    <img src={costorahMark} alt="" className={`${className} object-contain`} aria-hidden="true" />
  );
}
