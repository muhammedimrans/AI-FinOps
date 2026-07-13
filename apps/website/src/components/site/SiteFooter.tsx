import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { LogoMark } from "./SiteNav";

const columns = [
  {
    title: "Product",
    links: [
      { to: "/features", label: "Features" },
      { to: "/pricing", label: "Pricing" },
      { to: "/developers", label: "Developers" },
      { to: "/docs", label: "Docs" },
    ],
  },
  {
    title: "Company",
    links: [
      { to: "/about", label: "About" },
      { to: "/blog", label: "Blog" },
      { to: "/security", label: "Security" },
      { to: "/contact", label: "Contact" },
    ],
  },
  {
    title: "Legal",
    links: [
      { to: "/privacy", label: "Privacy" },
      { to: "/terms", label: "Terms" },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="relative overflow-hidden border-t border-white/5 bg-[#060810]">
      <div className="pointer-events-none absolute inset-x-0 -top-24 h-48 bg-[radial-gradient(ellipse_50%_100%_at_50%_0%,rgba(20,217,211,0.08),transparent_70%)]" />
      <div className="relative mx-auto max-w-[80rem] px-6 py-16">
        <div className="grid gap-12 md:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <Link to="/" className="flex items-center gap-2.5">
              <LogoMark />
              <span className="font-display text-lg font-semibold">Costorah</span>
            </Link>
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted-foreground">
              AI Cost Intelligence for modern teams. Monitor, optimize, and forecast AI spending
              across every provider.
            </p>
            <Link
              to="/signup"
              className="btn-brand mt-6 inline-flex px-4 py-2 text-[0.8125rem] hover:scale-[1.02] hover:brightness-105 active:scale-[0.98]"
            >
              Start free
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
          {columns.map((col) => (
            <div key={col.title}>
              <div className="eyebrow">{col.title}</div>
              <ul className="mt-5 flex flex-col gap-3">
                {col.links.map((l) => (
                  <li key={l.to}>
                    <Link
                      to={l.to}
                      className="text-sm text-foreground/70 transition-colors hover:text-foreground"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-16 flex flex-col items-start justify-between gap-4 border-t border-white/5 pt-8 text-xs text-muted-foreground md:flex-row md:items-center">
          <div>© {new Date().getFullYear()} Costorah, Inc. All rights reserved.</div>
          <div className="flex items-center gap-2">
            <span className="relative flex size-2">
              <span className="absolute inset-0 animate-ping rounded-full bg-[#14D9D3] opacity-60" />
              <span className="relative size-2 rounded-full bg-[#14D9D3] shadow-[0_0_10px_#14D9D3]" />
            </span>
            All systems operational
          </div>
        </div>
      </div>
    </footer>
  );
}
