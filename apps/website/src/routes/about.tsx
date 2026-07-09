import { createFileRoute } from "@tanstack/react-router";
import { StubPage } from "@/components/site/StubPage";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About — Costorah" },
      {
        name: "description",
        content: "We're building the financial control plane for the AI era.",
      },
      { property: "og:title", content: "About — Costorah" },
      { property: "og:description", content: "The financial control plane for the AI era." },
    ],
  }),
  component: () => (
    <StubPage
      eyebrow="About"
      title="The financial control plane for the AI era."
      description="We help modern teams understand every AI dollar — so they can build faster with confidence."
    />
  ),
});
