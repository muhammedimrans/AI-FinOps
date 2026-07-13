import { type ReactNode } from "react";
import { SiteNav } from "./SiteNav";
import { SiteFooter } from "./SiteFooter";

export function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className="dark min-h-screen bg-[#05070A] text-foreground">
      <SiteNav />
      <main>{children}</main>
      <SiteFooter />
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
}) {
  return (
    <section className="relative overflow-hidden border-b border-white/5">
      <div
        className="absolute inset-0 opacity-60"
        style={{ background: "var(--gradient-hero)" }}
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-4xl px-6 py-24 text-center md:py-32">
        {eyebrow && (
          <div className="mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs font-medium text-muted-foreground">
            <span className="size-1.5 rounded-full bg-[#14D9D3]" />
            {eyebrow}
          </div>
        )}
        <h1 className="font-display text-4xl font-semibold tracking-tight md:text-6xl">{title}</h1>
        {description && (
          <p className="mx-auto mt-6 max-w-2xl text-base text-muted-foreground md:text-lg">
            {description}
          </p>
        )}
      </div>
    </section>
  );
}
