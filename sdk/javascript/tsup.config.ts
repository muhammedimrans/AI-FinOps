import { defineConfig } from "tsup";

export default defineConfig({
  entry: [
    "src/index.ts",
    "src/express.ts",
    "src/node.ts",
    "src/lambda.ts",
    "src/cloudflare.ts",
    "src/next.ts",
    "src/nest/index.ts",
  ],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  target: "es2020",
  tsconfig: "tsconfig.build.json",
  // @nestjs/common, @nestjs/core, and rxjs are peerDependencies (see
  // package.json) — never bundled into dist/nest/*, so a consumer's own
  // installed Nest version is what actually runs at their app's
  // runtime, not a copy frozen at this SDK's build time.
  external: ["@nestjs/common", "@nestjs/core", "rxjs"],
  // The instrumentation module uses createRequire(import.meta.url) to
  // synchronously load provider SDKs from ESM code; `shims` makes esbuild
  // rewrite import.meta.url to a working equivalent in the CJS build too
  // (otherwise it becomes an empty string there).
  shims: true,
});
