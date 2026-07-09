import { Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import type { ReactNode } from "react";

export function StubPage({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <SiteLayout>
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <section className="mx-auto max-w-4xl px-6 py-16">
        {children ?? (
          <div className="rounded-2xl border border-white/10 bg-[#0C1117] p-8 text-center">
            <p className="text-muted-foreground">
              This page is coming soon. In the meantime, get started or reach out.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link
                to="/signup"
                className="rounded-full bg-gradient-brand px-5 py-2.5 text-sm font-medium text-primary-foreground"
              >
                Start free
              </Link>
              <Link
                to="/contact"
                className="rounded-full border border-white/10 bg-white/[0.03] px-5 py-2.5 text-sm font-medium"
              >
                Contact sales
              </Link>
            </div>
          </div>
        )}
      </section>
    </SiteLayout>
  );
}
