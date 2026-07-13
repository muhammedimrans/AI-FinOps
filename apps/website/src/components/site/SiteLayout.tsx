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
      <div className="aurora opacity-70" aria-hidden="true" />
      <div className="absolute inset-0 bg-grid opacity-40 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent_75%)]" />
      <div className="relative mx-auto max-w-4xl px-6 py-24 text-center md:py-32">
        {eyebrow && (
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 backdrop-blur">
            <span className="size-1.5 rounded-full bg-[#14D9D3] shadow-[0_0_8px_#14D9D3]" />
            <span className="eyebrow">{eyebrow}</span>
          </div>
        )}
        <h1 className="display-xl">{title}</h1>
        {description && (
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground md:text-lg">
            {description}
          </p>
        )}
      </div>
    </section>
  );
}
