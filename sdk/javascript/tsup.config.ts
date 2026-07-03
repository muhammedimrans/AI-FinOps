import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  target: "es2020",
  tsconfig: "tsconfig.build.json",
  // The instrumentation module uses createRequire(import.meta.url) to
  // synchronously load provider SDKs from ESM code; `shims` makes esbuild
  // rewrite import.meta.url to a working equivalent in the CJS build too
  // (otherwise it becomes an empty string there).
  shims: true,
});
