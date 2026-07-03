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
  //
  // @langchain/core must stay external for a correctness reason, not
  // just a size one: LangChainInstrumentor's registerConfigureHook()/
  // setContextVariable() only work if they operate on the exact same
  // @langchain/core module instance that the consumer's own
  // @langchain/openai (or other @langchain/* package) resolves at
  // runtime — found empirically when tsup bundled @langchain/core's
  // source into dist/, creating a second, independent module instance
  // whose configure-hook registry the real CallbackManager never reads
  // from, so every callback silently never fired.
  external: ["@nestjs/common", "@nestjs/core", "rxjs", "@langchain/core"],
  // The instrumentation module uses createRequire(import.meta.url) to
  // synchronously load provider SDKs from ESM code; `shims` makes esbuild
  // rewrite import.meta.url to a working equivalent in the CJS build too
  // (otherwise it becomes an empty string there).
  shims: true,
});
