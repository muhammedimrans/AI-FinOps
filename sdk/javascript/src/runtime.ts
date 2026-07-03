/**
 * Runtime and framework detection (EP-18.6). Used by the framework
 * integrations to report which JavaScript runtime/framework they're
 * running under (surfaced in captured context as `runtimeVersion`/
 * `frameworkVersion`) and by `detectFrameworks()` for the same
 * best-effort "what's installed" reporting Python's `costorah init`/
 * `doctor` CLI already does — there is no JS-side CLI in this SDK (the
 * `costorah` console script is a Python-only artifact, see
 * `sdk/docs/RUNTIME_COMPATIBILITY.md`), so this module is the
 * programmatic equivalent, importable directly by application code.
 */

export type Runtime =
  | "node"
  | "bun"
  | "deno"
  | "cloudflare-workers"
  | "lambda"
  | "browser"
  | "unknown";

interface GlobalWithRuntimeMarkers {
  Deno?: { version?: { deno?: string } };
  Bun?: { version?: string };
  navigator?: { userAgent?: string };
  window?: unknown;
  process?: {
    env?: Record<string, string | undefined>;
    versions?: Record<string, string | undefined>;
  };
}

function globalMarkers(): GlobalWithRuntimeMarkers {
  return globalThis as unknown as GlobalWithRuntimeMarkers;
}

/**
 * Detects the current JavaScript runtime. Order matters: Bun and Deno
 * both also expose a Node-compatible `process` global, so their own
 * markers (`Bun`/`Deno` globals) are checked first; Lambda is detected
 * via an env var Node also has access to, so it's checked before the
 * generic "node" fallback; Cloudflare Workers has no `process` global
 * at all under its native runtime (only under `nodejs_compat`), so its
 * `navigator.userAgent` marker — the mechanism Cloudflare's own docs
 * recommend — is checked independently of the `process`-based checks.
 */
export function detectRuntime(): Runtime {
  const g = globalMarkers();

  if (typeof g.Deno !== "undefined") return "deno";
  if (typeof g.Bun !== "undefined" || g.process?.versions?.bun) return "bun";
  if (g.navigator?.userAgent === "Cloudflare-Workers") return "cloudflare-workers";
  if (g.process?.env?.AWS_LAMBDA_FUNCTION_NAME) return "lambda";
  if (g.process?.versions?.node) return "node";
  if (typeof g.window !== "undefined") return "browser";
  return "unknown";
}

/** The runtime's own reported version string (Node/Bun/Deno version,
 * or `undefined` when not applicable/detectable — e.g. Cloudflare
 * Workers exposes no runtime version to user code). */
export function detectRuntimeVersion(): string | undefined {
  const g = globalMarkers();
  const runtime = detectRuntime();
  switch (runtime) {
    case "deno":
      return g.Deno?.version?.deno;
    case "bun":
      return g.Bun?.version ?? g.process?.versions?.bun;
    case "node":
    case "lambda":
      return g.process?.versions?.node;
    default:
      return undefined;
  }
}

const FRAMEWORK_PACKAGES: Record<string, string> = {
  express: "express",
  nestjs: "@nestjs/core",
  next: "next",
};

/**
 * Best-effort detection of which supported JS frameworks are
 * installed, via dynamic `import()` (works under both ESM and the
 * CJS build, and doesn't require Node-specific `require.resolve`, so
 * it degrades to "none detected" rather than throwing on runtimes
 * without a resolvable module graph, e.g. Cloudflare Workers).
 */
export async function detectFrameworks(): Promise<string[]> {
  const detected: string[] = [];
  for (const [label, moduleName] of Object.entries(FRAMEWORK_PACKAGES)) {
    try {
      await import(moduleName);
      detected.push(label);
    } catch {
      // not installed / not resolvable in this runtime — expected, not
      // an error condition.
    }
  }
  return detected;
}
