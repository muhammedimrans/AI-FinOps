import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About — Costorah" },
      {
        name: "description",
        content: "We're building the financial control plane for the AI era.",
      },
      { property: "og:title", content: "About — Costorah" },
      { property: "og:description", content: "The financial control plane for the AI era." },
    ],
  }),
  component: About,
});

const values = [
  {
    title: "Builders first",
    body: "Every feature ships behind an API and an SDK. If a developer can't automate it, we didn't finish it.",
  },
  {
    title: "Trust by default",
    body: "Encrypted, auditable, and yours. We store the least data possible to do the job well — usage metadata, never prompt or completion content.",
  },
  {
    title: "Clarity over hype",
    body: "AI is powerful and expensive. We help you tell the difference — with real numbers, not narratives. If something isn't built yet, we say so.",
  },
];

function About() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="About"
        title="The financial control plane for the AI era."
        description="We help teams understand every AI dollar — so they can build faster with confidence."
      />
      <section className="mx-auto max-w-4xl px-6 py-16">
        <div className="space-y-6 text-lg leading-relaxed text-foreground/90">
          <p>
            AI is one of the fastest-growing line items on the modern engineering budget — and one
            of the least understood. Bills arrive weeks late, attribution across teams and providers
            is hard, and forecasting is often guesswork.
          </p>
          <p>
            Costorah is our answer: unified visibility across every AI provider you use, sensible
            budgets and alerts, and analytics your team can actually act on. We're early — this
            product is under active, continuous development, and we'd rather be upfront about what's
            shipped today versus what's still on the roadmap than oversell either.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-24">
        <div className="grid gap-4 md:grid-cols-3">
          {values.map((v) => (
            <div key={v.title} className="rounded-2xl border border-white/10 bg-[#0C1117] p-6">
              <h3 className="font-display text-lg font-semibold">{v.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{v.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-20 flex flex-wrap justify-center gap-3">
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
            Say hello
          </Link>
        </div>
      </section>
    </SiteLayout>
  );
}
