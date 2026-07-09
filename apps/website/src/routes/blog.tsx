import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

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
  component: () => (
    <StubPage
      eyebrow="Blog"
      title="From the Costorah team"
      description="Stories, patterns, and playbooks from teams doing AI FinOps well."
    />
  ),
});
