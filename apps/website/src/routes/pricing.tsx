import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import { Check } from "lucide-react";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — Costorah" },
      {
        name: "description",
        content:
          "Free forever for individuals and small teams. Team and Enterprise plans are coming soon.",
      },
      { property: "og:title", content: "Pricing — Costorah" },
      { property: "og:description", content: "Simple pricing that scales with you." },
    ],
  }),
  component: Pricing,
});

const tiers: Array<{
  name: string;
  price: string;
  cadence: string;
  tagline: string;
  highlight?: boolean;
  comingSoon?: boolean;
  cta: { label: string; to: "/signup" | "/contact" };
  features: string[];
}> = [
  {
    name: "Free",
    price: "$0",
    cadence: "forever",
    tagline: "For individuals and side projects.",
    cta: { label: "Start free", to: "/signup" },
    features: [
      "Connect every supported provider",
      "Real-time usage dashboard",
      "Budgets & in-app alerts",
      "Role-based access control",
      "Python & JavaScript SDKs",
    ],
  },
  {
    name: "Team",
    price: "Coming soon",
    cadence: "",
    tagline: "For teams shipping AI features to production.",
    highlight: true,
    comingSoon: true,
    cta: { label: "Join the waitlist", to: "/contact" },
    features: [
      "Everything in Free",
      "Higher usage limits",
      "Longer data retention",
      "Priority support",
    ],
  },
  {
    name: "Enterprise",
    price: "Coming soon",
    cadence: "",
    tagline: "For regulated industries and larger orgs.",
    comingSoon: true,
    cta: { label: "Contact sales", to: "/contact" },
    features: [
      "Everything in Team",
      "SSO & advanced RBAC",
      "Custom retention",
      "Dedicated support",
    ],
  },
];

const faqs = [
  {
    q: "How is spend tracked?",
    a: "We collect usage via provider APIs, either through a manual sync or an automatic background scheduler.",
  },
  {
    q: "Do you store prompts or completions?",
    a: "No. We store usage metadata — tokens, cost, model, and timestamps — never prompt or completion content.",
  },
  {
    q: "When will paid plans be available?",
    a: "Team and Enterprise billing are on our roadmap. Everything on the Free plan is fully functional today.",
  },
  {
    q: "Is there a free tier?",
    a: "Yes — Free is free forever, no credit card required, with no artificial feature limits.",
  },
];

function Pricing() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Pricing"
        title="Simple pricing that scales with you."
        description="Start free today. Team and Enterprise plans with billing are coming soon."
      />
      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-6 md:grid-cols-3">
          {tiers.map((t) => (
            <div
              key={t.name}
              className={`relative rounded-2xl border p-8 ${
                t.highlight
                  ? "border-[#14D9D3]/40 bg-gradient-to-b from-[#14D9D3]/[0.08] to-transparent"
                  : "border-white/10 bg-[#0C1117]"
              }`}
            >
              {t.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-brand px-3 py-1 text-xs font-semibold text-primary-foreground">
                  Coming soon
                </div>
              )}
              <div className="font-display text-xl font-semibold">{t.name}</div>
              <p className="mt-1 text-sm text-muted-foreground">{t.tagline}</p>
              <div className="mt-6 flex items-baseline gap-2">
                <span className="font-display text-4xl font-semibold tracking-tight">
                  {t.price}
                </span>
                {t.cadence && <span className="text-sm text-muted-foreground">{t.cadence}</span>}
              </div>
              <Link
                to={t.cta.to}
                className={`mt-6 inline-flex w-full items-center justify-center rounded-full px-5 py-2.5 text-sm font-medium ${
                  t.highlight && !t.comingSoon
                    ? "bg-gradient-brand text-primary-foreground"
                    : "border border-white/10 bg-white/[0.03] text-foreground"
                }`}
              >
                {t.cta.label}
              </Link>
              <ul className="mt-8 flex flex-col gap-3">
                {t.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <Check className="mt-0.5 size-4 shrink-0 text-[#14D9D3]" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-24">
          <h2 className="font-display text-3xl font-semibold tracking-tight">Frequently asked</h2>
          <div className="mt-8 grid gap-4 md:grid-cols-2">
            {faqs.map((f) => (
              <div key={f.q} className="rounded-2xl border border-white/10 bg-[#0C1117] p-6">
                <div className="font-medium">{f.q}</div>
                <p className="mt-2 text-sm text-muted-foreground">{f.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </SiteLayout>
  );
}
