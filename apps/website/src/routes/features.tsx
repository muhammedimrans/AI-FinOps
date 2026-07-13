import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import {
  Activity,
  Wallet,
  LineChart,
  Shield,
  Bell,
  Users,
  GitBranch,
  Gauge,
  Database,
  Layers,
  KeyRound,
} from "lucide-react";

export const Route = createFileRoute("/features")({
  head: () => ({
    meta: [
      { title: "Features — Costorah" },
      {
        name: "description",
        content:
          "Unified AI spend, live monitoring, budgets, and analytics across every provider you use.",
      },
      { property: "og:title", content: "Features — Costorah" },
      { property: "og:description", content: "Every capability a modern AI team needs." },
    ],
  }),
  component: Features,
});

const groups = [
  {
    title: "Visibility",
    blurb: "One pane of glass across every model, provider, and team.",
    items: [
      {
        icon: Activity,
        title: "Unified spend",
        body: "OpenAI, Anthropic, Google Gemini, Azure OpenAI, OpenRouter, Grok, and Ollama — one dashboard.",
      },
      {
        icon: Database,
        title: "Usage collection",
        body: "Manual or automatic background sync pulls usage from every connected provider.",
      },
      {
        icon: Layers,
        title: "Multi-workspace",
        body: "Personal and team workspaces with clean, role-based isolation.",
      },
    ],
  },
  {
    title: "Control",
    blurb: "Guardrails that keep spend visible before it surprises you.",
    items: [
      {
        icon: Wallet,
        title: "Budgets",
        body: "Org, project, provider, and model-level budgets with configurable alert thresholds.",
      },
      {
        icon: Bell,
        title: "In-app alerts",
        body: "Budget and anomaly alerts land in your notification center today. Email, Slack, and webhook delivery are coming soon.",
      },
      {
        icon: Shield,
        title: "Role-based access",
        body: "Owner, Admin, Member, and Viewer roles, with an audit trail on every change.",
      },
    ],
  },
  {
    title: "Analytics & Forecast",
    blurb: "Understand where every AI dollar goes.",
    items: [
      {
        icon: LineChart,
        title: "Cost analytics",
        body: "Filterable breakdowns by project, provider, and model, plus a usage heatmap.",
      },
      {
        icon: GitBranch,
        title: "Provider & model comparison",
        body: "Side-by-side spend and usage across every provider and model you connect.",
      },
      {
        icon: Users,
        title: "Team management",
        body: "Invite teammates, assign roles, and manage API keys from one workspace.",
      },
    ],
  },
  {
    title: "Built for developers",
    blurb: "Instrument your app in a single line of code.",
    items: [
      {
        icon: KeyRound,
        title: "Python & JavaScript SDKs",
        body: "Drop-in wrappers for your existing provider client. More languages are coming soon.",
      },
      {
        icon: Gauge,
        title: "Realtime dashboard",
        body: "Live KPIs and charts over WebSocket, with an automatic polling fallback.",
      },
      {
        icon: Database,
        title: "REST API & CLI",
        body: "Everything in the dashboard is available through a versioned API and a CLI.",
      },
    ],
  },
] as const;

function Features() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Features"
        title="Everything a modern AI team needs, today."
        description="Costorah unifies visibility, control, and analytics across every AI provider you use. We're honest about what's shipped and what's still coming — see below."
      />
      <section className="mx-auto max-w-7xl px-6 py-20">
        <div className="flex flex-col gap-24">
          {groups.map((g) => (
            <div key={g.title}>
              <div className="mb-10 flex flex-col items-start gap-2 md:flex-row md:items-end md:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-widest text-[#14D9D3]">
                    {g.title}
                  </div>
                  <h2 className="mt-2 font-display text-3xl font-semibold tracking-tight md:text-4xl">
                    {g.blurb}
                  </h2>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                {g.items.map((it) => (
                  <div
                    key={it.title}
                    className="rounded-2xl border border-white/10 bg-[#0C1117] p-6 transition-colors hover:border-[#14D9D3]/30"
                  >
                    <div className="flex size-10 items-center justify-center rounded-lg bg-[#14D9D3]/10 text-[#14D9D3]">
                      <it.icon className="size-5" />
                    </div>
                    <h3 className="mt-4 font-display text-lg font-semibold">{it.title}</h3>
                    <p className="mt-2 text-sm text-muted-foreground">{it.body}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-24 rounded-3xl border border-white/10 bg-gradient-to-b from-white/[0.04] to-transparent p-10 text-center">
          <h3 className="font-display text-2xl font-semibold md:text-3xl">
            See it on your own AI stack
          </h3>
          <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
            Connect a provider in minutes. Free forever for individuals and small teams.
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
              Talk to us
            </Link>
          </div>
        </div>
      </section>
    </SiteLayout>
  );
}
