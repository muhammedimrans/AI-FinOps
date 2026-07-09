import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/security")({
  head: () => ({
    meta: [
      { title: "Security — Costorah" },
      {
        name: "description",
        content:
          "Enterprise-grade security: RBAC, SSO, audit logs, encrypted keys, SOC 2 and GDPR readiness.",
      },
      { property: "og:title", content: "Security — Costorah" },
      { property: "og:description", content: "Enterprise-grade security from day one." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Security"
      title="Enterprise-grade from day one."
      description="Designed with the controls that regulated industries require."
    />
  ),
});
