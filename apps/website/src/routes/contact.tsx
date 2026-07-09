import { createFileRoute } from "@tanstack/react-router";
import { SiteLayout, PageHeader } from "@/components/site/SiteLayout";

export const Route = createFileRoute("/contact")({
  head: () => ({
    meta: [
      { title: "Contact — Costorah" },
      {
        name: "description",
        content: "Talk to our team about pricing, security, and enterprise deployments.",
      },
      { property: "og:title", content: "Contact — Costorah" },
      { property: "og:description", content: "Talk to our team." },
    ],
  }),
  component: Contact,
});

function Contact() {
  return (
    <SiteLayout>
      <PageHeader
        eyebrow="Contact"
        title="Talk to our team."
        description="Tell us about your AI workload. We'll show you exactly how much you could save."
      />
      <section className="mx-auto max-w-2xl px-6 pb-24">
        <form
          onSubmit={(e) => e.preventDefault()}
          className="space-y-4 rounded-2xl border border-white/10 bg-[#0C1117] p-6"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" placeholder="Ada Lovelace" />
            <Field label="Work email" type="email" placeholder="you@company.com" />
          </div>
          <Field label="Company" placeholder="Acme Inc." />
          <div>
            <label className="text-sm text-muted-foreground">How can we help?</label>
            <textarea
              rows={5}
              placeholder="Tell us about your AI stack and what you're trying to solve."
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40"
            />
          </div>
          <button
            type="submit"
            className="w-full rounded-full bg-gradient-brand px-5 py-3 text-sm font-medium text-primary-foreground"
          >
            Send message
          </button>
        </form>
      </section>
    </SiteLayout>
  );
}

function Field({
  label,
  ...rest
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label className="text-sm text-muted-foreground">{label}</label>
      <input
        {...rest}
        className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40"
      />
    </div>
  );
}
