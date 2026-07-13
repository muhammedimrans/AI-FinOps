import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import { Terminal, Package, Boxes, FileCode, Github } from "lucide-react";

export const Route = createFileRoute("/developers")({
  head: () => ({
    meta: [
      { title: "Developers — Costorah" },
      {
        name: "description",
        content: "Python and JavaScript/TypeScript SDKs, a REST API, and a CLI — instrument once.",
      },
      { property: "og:title", content: "Developers — Costorah" },
      { property: "og:description", content: "First-class SDKs and a REST API." },
    ],
  }),
  component: Developers,
});

const sdkTs = `import { Costorah } from "@costorah/sdk";
import OpenAI from "openai";

const cost = new Costorah({ apiKey: process.env.COSTORAH_KEY });
const openai = cost.wrap(new OpenAI());

// Every call is now tracked and attributed to a project.
await openai.chat.completions.create(
  { model: "gpt-4o", messages: [{ role: "user", content: "Hi" }] },
  { costorah: { project: "onboarding-summary" } },
);`;

const sdkPy = `from costorah import Costorah
from anthropic import Anthropic

cost = Costorah(api_key=os.environ["COSTORAH_KEY"])
anthropic = cost.wrap(Anthropic())

anthropic.messages.create(
    model="claude-3-5-sonnet",
    messages=[{"role": "user", "content": "Hi"}],
    costorah={"project": "onboarding-summary"},
)`;

const capabilities = [
  {
    icon: Package,
    title: "SDKs",
    body: "Python and JavaScript/TypeScript today, with drop-in wrappers for OpenAI and Anthropic. More languages and providers are coming soon.",
  },
  {
    icon: Terminal,
    title: "CLI",
    body: "A scriptable command-line client for local development and diagnostics.",
  },
  {
    icon: FileCode,
    title: "REST API",
    body: "A single, versioned REST API backs the dashboard, the SDKs, and the CLI — nothing is dashboard-only.",
  },
  {
    icon: Boxes,
    title: "Webhooks & Terraform",
    body: "Coming soon — subscribe to budget and anomaly events, and manage workspaces as code.",
  },
];

function Developers() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Developers"
        title="Instrument once. Ship in minutes."
        description="Wrap your existing provider SDK and get cost tracking and budgets out of the box."
      />
      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-6 lg:grid-cols-2">
          <CodeCard title="TypeScript" code={sdkTs} />
          <CodeCard title="Python" code={sdkPy} />
        </div>

        <div className="mt-16 rounded-2xl border border-white/10 bg-[#0C1117] p-8">
          <h3 className="font-display text-xl font-semibold">Everything in one API</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            A single REST endpoint, versioned and stable. Or use our typed SDKs — same shape
            everywhere.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/docs"
              className="rounded-full bg-gradient-brand px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              Read the docs
            </Link>
            <a
              href="https://github.com/costorah"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-sm font-medium"
            >
              <Github className="size-4" />
              View on GitHub
            </a>
          </div>
        </div>

        <div className="mt-20 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {capabilities.map((c) => (
            <div key={c.title} className="rounded-2xl border border-white/10 bg-[#0C1117] p-6">
              <div className="flex size-10 items-center justify-center rounded-lg bg-[#14D9D3]/10 text-[#14D9D3]">
                <c.icon className="size-5" />
              </div>
              <h3 className="mt-4 font-display text-lg font-semibold">{c.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{c.body}</p>
            </div>
          ))}
        </div>
      </section>
    </SiteLayout>
  );
}

function CodeCard({ title, code }: { title: string; code: string }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0A0E13]">
      <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="size-2.5 rounded-full bg-white/10" />
          <span className="size-2.5 rounded-full bg-white/10" />
          <span className="size-2.5 rounded-full bg-white/10" />
        </div>
        <div className="text-xs text-muted-foreground">{title}</div>
      </div>
      <pre className="overflow-x-auto p-5 text-[13px] leading-relaxed">
        <code className="font-mono text-foreground/90">{code}</code>
      </pre>
    </div>
  );
}
