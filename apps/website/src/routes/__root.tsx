import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";

// EP-25.3.3 — cache-busting version tag for the favicon/icon set below.
// Browsers cache /favicon.ico extremely aggressively (often ignoring normal
// HTTP cache-control and persisting across hard refreshes), unlike Vite's
// content-hashed imported assets — a bare `/favicon.ico` URL that never
// changes can keep serving a stale icon indefinitely even after the file on
// disk is replaced. Appending a query string tied to the source artwork's
// own content hash forces every browser to treat a real logo change as a
// new URL. Bump this whenever apps/website/src/assets/BrowserFavicon.png
// changes (the browser-tab favicon set is sourced from BrowserFavicon.png,
// a separate asset from Costorah.png, which remains the in-app logo source
// for SiteNav/CostorahLogo).
const FAVICON_VERSION = "af963841";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-gradient-brand">404</h1>
        <h2 className="mt-4 text-xl font-semibold">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-full bg-gradient-brand px-5 py-2.5 text-sm font-medium text-primary-foreground transition-transform hover:scale-[1.02]"
          >
            Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight">Something went wrong</h1>
        <p className="mt-2 text-sm text-muted-foreground">Please try refreshing, or return home.</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-full bg-gradient-brand px-5 py-2.5 text-sm font-medium text-primary-foreground"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-full border border-white/10 bg-white/5 px-5 py-2.5 text-sm font-medium"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { name: "theme-color", content: "#05070A" },
      { title: "Costorah — AI Cost Intelligence for Modern Teams" },
      {
        name: "description",
        content:
          "Monitor, optimize, and forecast AI spending across OpenAI, Anthropic, Google, Azure, and every provider — from one unified platform.",
      },
      { name: "author", content: "Costorah" },
      { property: "og:title", content: "Costorah — AI Cost Intelligence for Modern Teams" },
      {
        property: "og:description",
        content: "Unified AI FinOps: monitor, optimize, and forecast spend across every provider.",
      },
      { property: "og:type", content: "website" },
      { property: "og:image", content: `/og-image.png?v=${FAVICON_VERSION}` },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: "Costorah — AI Cost Intelligence" },
      { name: "twitter:description", content: "Unified AI FinOps across every provider." },
      { name: "twitter:image", content: `/og-image.png?v=${FAVICON_VERSION}` },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: `/favicon.ico?v=${FAVICON_VERSION}`, type: "image/x-icon" },
      {
        rel: "icon",
        href: `/favicon-32x32.png?v=${FAVICON_VERSION}`,
        type: "image/png",
        sizes: "32x32",
      },
      {
        rel: "icon",
        href: `/favicon-16x16.png?v=${FAVICON_VERSION}`,
        type: "image/png",
        sizes: "16x16",
      },
      {
        rel: "apple-touch-icon",
        href: `/apple-touch-icon.png?v=${FAVICON_VERSION}`,
        sizes: "180x180",
      },
      { rel: "manifest", href: `/site.webmanifest?v=${FAVICON_VERSION}` },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  );
}
