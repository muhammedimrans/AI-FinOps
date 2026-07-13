import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";
import { Shield, Lock, KeyRound, Eye, Users, Clock } from "lucide-react";

export const Route = createFileRoute("/security")({
  head: () => ({
    meta: [
      { title: "Security — Costorah" },
      {
        name: "description",
        content:
          "Encrypted provider credentials, role-based access control, and a full audit trail — built in from day one.",
      },
      { property: "og:title", content: "Security — Costorah" },
      { property: "og:description", content: "Security, built in from day one." },
    ],
  }),
  component: Security,
});

const pillars = [
  {
    icon: Lock,
    title: "Encrypted in transit and at rest",
    body: "TLS everywhere in transit. Provider credentials are encrypted at rest, per connection, and are never returned in plain text by our API.",
  },
  {
    icon: KeyRound,
    title: "Live credential validation",
    body: "Every connected provider key is validated on save and can be re-tested at any time, so you always know if a credential is actually working.",
  },
  {
    icon: Users,
    title: "Role-based access control",
    body: "Owner, Admin, Member, and Viewer roles map to exactly what each teammate can see and change in a workspace.",
  },
  {
    icon: Eye,
    title: "Audit trail",
    body: "Every sensitive action — invites, role changes, credential rotation — is logged.",
  },
  {
    icon: Shield,
    title: "Least data by default",
    body: "We store usage metadata — tokens, cost, model, timestamps. We never collect prompt or completion content.",
  },
  {
    icon: Clock,
    title: "One account system",
    body: "A single, unified authentication system backs both the marketing site and the dashboard — no parallel account stores.",
  },
];

const roadmap = [
  "Single sign-on (SSO / SAML)",
  "SCIM provisioning",
  "Bring your own key management (KMS)",
  "Formal compliance certifications (SOC 2, etc.)",
];

function Security() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Security & Trust"
        title="Security, built in from day one."
        description="We're an early-stage product — here's exactly what's shipped today, and what's still on the roadmap."
      />
      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {pillars.map((p) => (
            <div key={p.title} className="rounded-2xl border border-white/10 bg-[#0C1117] p-6">
              <div className="flex size-10 items-center justify-center rounded-lg bg-[#14D9D3]/10 text-[#14D9D3]">
                <p.icon className="size-5" />
              </div>
              <h3 className="mt-4 font-display text-lg font-semibold">{p.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{p.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-20">
          <div className="flex items-center gap-3">
            <Shield className="size-5 text-[#14D9D3]" />
            <h2 className="font-display text-2xl font-semibold tracking-tight">On the roadmap</h2>
          </div>
          <p className="mt-3 max-w-2xl text-sm text-muted-foreground">
            These are coming soon — we'd rather tell you what's next than claim it's already here.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {roadmap.map((r) => (
              <div
                key={r}
                className="flex items-center justify-between rounded-xl border border-white/10 bg-[#0C1117] px-5 py-4"
              >
                <span className="font-medium">{r}</span>
                <span className="text-xs text-muted-foreground">Coming soon</span>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-20 rounded-3xl border border-white/10 bg-gradient-to-b from-white/[0.04] to-transparent p-10 text-center">
          <h3 className="font-display text-2xl font-semibold">Questions about security?</h3>
          <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
            Reach out and we'll walk you through exactly how your data is handled.
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
