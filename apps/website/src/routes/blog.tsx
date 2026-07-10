import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import { BookOpen } from "lucide-react";

export const Route = createFileRoute("/blog")({
  head: () => ({
    meta: [
      { title: "Blog — Costorah" },
      {
        name: "description",
        content: "Stories, patterns, and playbooks from teams doing AI FinOps well.",
      },
      { property: "og:title", content: "Blog — Costorah" },
      { property: "og:description", content: "Stories from teams doing AI FinOps well." },
    ],
  }),
  component: Blog,
});

function Blog() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Blog"
        title="From the Costorah team"
        description="Stories, patterns, and playbooks from teams doing AI FinOps well."
      />
      <section className="mx-auto max-w-3xl px-6 py-24 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-[#0C1117] text-[#14D9D3]">
          <BookOpen className="h-6 w-6" />
        </div>
        <h2 className="mt-6 font-display text-2xl font-semibold">Coming soon</h2>
        <p className="mx-auto mt-3 max-w-md text-muted-foreground">
          We're writing our first posts on AI cost attribution, budgets, and what we're building
          next. Check back soon.
        </p>
        <Link
          to="/signup"
          className="mt-8 inline-flex rounded-full bg-gradient-brand px-5 py-2.5 text-sm font-medium text-primary-foreground"
        >
          Start free in the meantime
        </Link>
      </section>
    </SiteLayout>
  );
}
