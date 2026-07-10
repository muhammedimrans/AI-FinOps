import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import { BookOpen, Rocket, Boxes, Shield, LineChart, Code2, Users } from "lucide-react";

export const Route = createFileRoute("/docs")({
  head: () => ({
    meta: [
      { title: "Documentation — Costorah" },
      {
        name: "description",
        content: "Guides, API references, SDKs, and examples to help you ship with Costorah.",
      },
      { property: "og:title", content: "Documentation — Costorah" },
      { property: "og:description", content: "Guides, API reference, and examples." },
    ],
  }),
  component: Docs,
});

const sections = [
  {
    icon: Rocket,
    title: "Get started",
    items: [
      "Quickstart",
      "Connect your first provider",
      "Instrument the SDK",
      "Set your first budget",
    ],
  },
  {
    icon: Boxes,
    title: "Core concepts",
    items: ["Workspaces & organizations", "Cost attribution", "Projects", "Budgets"],
  },
  {
    icon: Code2,
    title: "SDK reference",
    items: ["Python", "JavaScript / TypeScript", "More languages — coming soon"],
  },
  {
    icon: Boxes,
    title: "Supported providers",
    items: ["OpenAI", "Anthropic", "Google Gemini", "Azure OpenAI", "OpenRouter, Grok & Ollama"],
  },
  {
    icon: LineChart,
    title: "Observability",
    items: ["Live dashboard", "Usage heatmap", "Provider & model comparison", "Cost analytics"],
  },
  {
    icon: Shield,
    title: "Security",
    items: [
      "Encrypted credentials",
      "Role-based access control",
      "Audit trail",
      "SSO — coming soon",
    ],
  },
  {
    icon: Users,
    title: "Admin",
    items: ["Roles & permissions", "Team invitations", "API keys", "Billing — coming soon"],
  },
  {
    icon: BookOpen,
    title: "Playbooks",
    items: [
      "Rolling out budgets",
      "Connecting your first provider",
      "Reading the usage heatmap",
      "Inviting your team",
    ],
  },
] as const;

function Docs() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Documentation"
        title="Everything you need to ship with Costorah."
        description="Guides, API references, SDK docs, and playbooks. This index reflects what's shipped today — items marked 'coming soon' aren't live yet."
      />
      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {sections.map((s) => (
            <div key={s.title} className="rounded-2xl border border-white/10 bg-[#0C1117] p-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#14D9D3]/10 text-[#14D9D3]">
                <s.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 font-display text-lg font-semibold">{s.title}</h3>
              <ul className="mt-3 space-y-2">
                {s.items.map((i) => (
                  <li key={i}>
                    <span className="text-sm text-muted-foreground">{i}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-20 rounded-3xl border border-white/10 bg-gradient-to-b from-white/[0.04] to-transparent p-10 text-center">
          <h3 className="font-display text-2xl font-semibold">Can't find what you need?</h3>
          <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
            A full documentation site is on the way. In the meantime, reach out directly.
          </p>
          <Link
            to="/contact"
            className="mt-6 inline-flex rounded-full bg-gradient-brand px-5 py-2.5 text-sm font-medium text-primary-foreground"
          >
            Contact us
          </Link>
        </div>
      </section>
    </SiteLayout>
  );
}
