import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/developers")({
  head: () => ({
    meta: [
      { title: "Developers — Costorah" },
      {
        name: "description",
        content: "First-class SDKs, REST API, webhooks, CLI, and Terraform provider.",
      },
      { property: "og:title", content: "Developers — Costorah" },
      { property: "og:description", content: "First-class SDKs, REST API, and webhooks." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Developers"
      title="Ship in minutes. Instrument once."
      description="First-class SDKs for Python, JavaScript, Go, and Rust. Plus REST, webhooks, and a CLI."
    />
  ),
});
