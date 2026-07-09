import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Terms — Costorah" },
      { name: "description", content: "Terms of service for using Costorah." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Legal"
      title="Terms of Service"
      description="The terms that govern your use of Costorah."
    />
  ),
});
