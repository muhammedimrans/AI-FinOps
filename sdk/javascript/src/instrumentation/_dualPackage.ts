/**
 * Shared helper for the "dual package hazard": most modern npm SDKs ship
 * independently-built CJS (`*.js`) and ESM (`*.mjs`) twins of the same
 * module, each with its own class/prototype object. A client built via
 * `import X from "sdk"` (ESM entry) and one built via `require("sdk")`
 * (CJS entry) end up as instances of *different* classes even though
 * they're "the same" class conceptually — patching only one twin's
 * prototype silently misses calls made through the other, depending on
 * how the *consumer's* code happens to import the provider SDK.
 *
 * `createRequire` can synchronously load both twins (Node 22+ supports
 * `require()` of pure-ESM `.mjs` modules) without making `instrument()`
 * async, so every instrumentor that needs prototype-level patching goes
 * through this helper to patch (and later restore) every twin it can
 * resolve, not just one.
 */

import { createRequire } from "node:module";

import { InstrumentationError } from "./base.js";

const nodeRequire = createRequire(import.meta.url);

export function requireBothTwins(
  basePath: string,
  exportName: string,
): Record<string, unknown>[] {
  const protos: Record<string, unknown>[] = [];
  const seen = new Set<unknown>();
  for (const ext of [".js", ".mjs"]) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mod: any = nodeRequire(`${basePath}${ext}`);
      const proto = (mod[exportName] as { prototype: Record<string, unknown> })?.prototype;
      if (proto && !seen.has(proto)) {
        seen.add(proto);
        protos.push(proto);
      }
    } catch {
      // This twin isn't resolvable in the current runtime — the other
      // one (or neither, if the package isn't installed) still is.
    }
  }
  return protos;
}

export function requireBothTwinsOrThrow(
  basePath: string,
  exportName: string,
  packageName: string,
): Record<string, unknown>[] {
  const protos = requireBothTwins(basePath, exportName);
  if (protos.length === 0) {
    throw new InstrumentationError(
      `The '${packageName}' package is not installed. Install it with ` +
        `\`npm install ${packageName}\` to use this instrumentor.`,
    );
  }
  return protos;
}
