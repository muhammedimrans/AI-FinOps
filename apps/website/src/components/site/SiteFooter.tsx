import { Link } from "@tanstack/react-router";
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
    <footer className="border-t border-white/5 bg-[#05070A]">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-12 md:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <Link to="/" className="flex items-center gap-2">
              <LogoMark />
              <span className="font-display text-lg font-semibold">Costorah</span>
            </Link>
            <p className="mt-4 max-w-sm text-sm text-muted-foreground">
              AI Cost Intelligence for modern teams. Monitor, optimize, and forecast AI spending
              across every provider.
            </p>
          </div>
          {columns.map((col) => (
            <div key={col.title}>
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {col.title}
              </div>
              <ul className="mt-4 flex flex-col gap-3">
                {col.links.map((l) => (
                  <li key={l.to}>
                    <Link to={l.to} className="text-sm text-foreground/80 hover:text-foreground">
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
            <span className="inline-block size-2 rounded-full bg-[#14D9D3] shadow-[0_0_10px_#14D9D3]" />
            All systems operational
          </div>
        </div>
      </div>
    </footer>
  );
}
