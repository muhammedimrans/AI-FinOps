// Standalone from vite.config.ts (which is wrapped by
// @lovable.dev/vite-tanstack-config and doesn't expose a `test` field to
// extend) — this app had no test runner at all before EP-21.2. Scope is
// deliberately narrow: plain-function unit tests (validation schemas, the
// fetch-based API client) that don't need jsdom or a router test harness.
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
