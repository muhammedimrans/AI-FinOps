import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/features")({
  head: () => ({
    meta: [
      { title: "Features — Costorah" },
      {
        name: "description",
        content:
          "Every capability a modern AI team needs: unified spend, live monitoring, forecasting, and more.",
      },
      { property: "og:title", content: "Features — Costorah" },
      { property: "og:description", content: "Every capability a modern AI team needs." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Features"
      title="Every capability a modern AI team needs."
      description="Unified spend, live monitoring, budgets, forecasting, optimization, RBAC, SSO, and more."
    />
  ),
});
