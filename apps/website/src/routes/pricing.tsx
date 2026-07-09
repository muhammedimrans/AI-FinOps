import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — Costorah" },
      {
        name: "description",
        content:
          "Simple pricing that scales with you. Free forever for individuals and small teams.",
      },
      { property: "og:title", content: "Pricing — Costorah" },
      { property: "og:description", content: "Simple pricing that scales with you." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Pricing"
      title="Simple pricing that scales with you."
      description="Start free. Upgrade for advanced controls, forecasting, or compliance."
    />
  ),
});
