import { describe, expect, it, vi } from "vitest";

import { detectFrameworks, detectRuntime, detectRuntimeVersion } from "../src/runtime.js";

describe("detectRuntime", () => {
  it("detects the real runtime this test suite is running under (Node)", () => {
    // Node.js is what vitest actually runs under in this repo's CI/dev
    // environment — a real, not mocked, assertion.
    expect(detectRuntime()).toBe("node");
    expect(detectRuntimeVersion()).toBe(process.versions.node);
  });

  it("detects Bun via the process.versions.bun marker", () => {
    const original = process.versions.bun;
    process.versions.bun = "1.0.0";
    try {
      expect(detectRuntime()).toBe("bun");
    } finally {
      if (original === undefined) delete process.versions.bun;
      else process.versions.bun = original;
    }
  });

  it("detects Cloudflare Workers via the navigator.userAgent marker", () => {
    vi.stubGlobal("navigator", { userAgent: "Cloudflare-Workers" });
    try {
      expect(detectRuntime()).toBe("cloudflare-workers");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("detects Lambda via the AWS_LAMBDA_FUNCTION_NAME env var", () => {
    const original = process.env.AWS_LAMBDA_FUNCTION_NAME;
    process.env.AWS_LAMBDA_FUNCTION_NAME = "my-function";
    try {
      expect(detectRuntime()).toBe("lambda");
    } finally {
      if (original === undefined) delete process.env.AWS_LAMBDA_FUNCTION_NAME;
      else process.env.AWS_LAMBDA_FUNCTION_NAME = original;
    }
  });

  it("detects Deno via the Deno global marker", () => {
    vi.stubGlobal("Deno", { version: { deno: "1.40.0" } });
    try {
      expect(detectRuntime()).toBe("deno");
      expect(detectRuntimeVersion()).toBe("1.40.0");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("detectFrameworks", () => {
  it("detects every framework installed as a devDependency in this package", async () => {
    // express, @nestjs/core, and next's absence are all real, not
    // mocked — this package's own devDependencies double as the fixture.
    const frameworks = await detectFrameworks();
    expect(frameworks).toContain("express");
    expect(frameworks).toContain("nestjs");
    expect(frameworks).not.toContain("next");
  });
});
