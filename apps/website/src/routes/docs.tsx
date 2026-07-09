import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/docs")({
  head: () => ({
    meta: [
      { title: "Documentation — Costorah" },
      {
        name: "description",
        content: "Guides, API references, and examples to help you ship with Costorah.",
      },
      { property: "og:title", content: "Documentation — Costorah" },
      { property: "og:description", content: "Guides, API reference, and examples." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Docs"
      title="Documentation"
      description="Guides, API references, and examples to help you ship with Costorah."
    />
  ),
});
