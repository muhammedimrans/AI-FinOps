import { type ReactNode } from "react";
import { LogoMark } from "./SiteNav";

interface AuthCardProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

/**
 * Shared shell for every website auth page (login, signup) — EP-25.3.
 * Brings the marketing site's auth windows up to the same premium
 * treatment apps/dashboard's own Login.tsx already established (ambient
 * glow behind one unified glass panel, not two stacked bordered boxes),
 * reusing this site's own existing tokens throughout (`--gradient-hero`,
 * the shared `LogoMark`, the site's teal accent) rather than inventing a
 * second visual language. The landing page and every other route are
 * untouched — this component is only ever mounted from /login and
 * /signup.
 */
export function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <section className="relative overflow-hidden px-6 py-20 md:py-28">
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{ background: "var(--gradient-hero)" }}
        aria-hidden="true"
      />
      <div className="relative mx-auto flex max-w-md flex-col items-center">
        <div className="relative">
          <div
            className="absolute inset-0 -z-10 rounded-full bg-[#14D9D3]/30 blur-2xl"
            aria-hidden="true"
          />
          <LogoMark className="h-10 w-10" />
        </div>
        <h1 className="mt-5 text-center font-display text-3xl font-semibold tracking-tight md:text-4xl">
          {title}
        </h1>
        <p className="mt-2 text-center text-sm text-muted-foreground">{subtitle}</p>
        <div className="relative mt-9 w-full rounded-3xl border border-white/10 bg-white/[0.03] p-7 shadow-[0_0_70px_-20px_rgba(20,217,211,0.3)] backdrop-blur-xl sm:p-9">
          {children}
        </div>
      </div>
    </section>
  );
}
