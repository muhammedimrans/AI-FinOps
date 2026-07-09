import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy — Costorah" },
      { name: "description", content: "How Costorah handles data and respects your privacy." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="Legal"
      title="Privacy Policy"
      description="How we collect, use, and protect your data."
    />
  ),
});
