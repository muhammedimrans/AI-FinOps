import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  PROVIDER_BRAND_REGISTRY,
  getProviderBrand,
} from "../lib/providerCatalog";
import ProviderLogo from "../components/ProviderLogo";

// EP-26.0.4 — Provider Brand Registry
describe("PROVIDER_BRAND_REGISTRY", () => {
  const SUPPORTED = ["openai", "anthropic", "google", "openrouter", "azure_openai", "grok", "ollama"];
  const FUTURE_PLACEHOLDERS = ["deepseek", "llama", "mistral", "cohere", "qwen"];

  it("has an entry for all 7 supported providers", () => {
    for (const id of SUPPORTED) {
      expect(PROVIDER_BRAND_REGISTRY[id]).toBeDefined();
    }
  });

  it("has entries for all 5 future-ready placeholders", () => {
    for (const id of FUTURE_PLACEHOLDERS) {
      expect(PROVIDER_BRAND_REGISTRY[id]).toBeDefined();
    }
  });

  it("every entry has a non-empty logo, displayName, and capabilities list", () => {
    for (const brand of Object.values(PROVIDER_BRAND_REGISTRY)) {
      expect(brand.logo).toBeTruthy();
      expect(brand.displayName.length).toBeGreaterThan(0);
      expect(Array.isArray(brand.capabilities)).toBe(true);
    }
  });

  it("marks officialAsset accurately per the disclosed sourcing decision", () => {
    // Sourced from simple-icons (a redistributable, locally-stored SVG set).
    for (const id of ["anthropic", "google", "openrouter", "ollama", "deepseek", "llama", "mistral", "qwen"]) {
      expect(PROVIDER_BRAND_REGISTRY[id]!.officialAsset).toBe(true);
    }
    // No redistributable official mark was sourceable in this environment —
    // original monograms, disclosed as such.
    for (const id of ["openai", "azure_openai", "grok", "cohere"]) {
      expect(PROVIDER_BRAND_REGISTRY[id]!.officialAsset).toBe(false);
    }
  });

  it("Google's registry entry carries the EP-26.0.2 Platform/Service identity", () => {
    expect(PROVIDER_BRAND_REGISTRY["google"]!.platform).toBe("AI Studio");
    expect(PROVIDER_BRAND_REGISTRY["google"]!.service).toBe("Gemini API");
  });
});

describe("getProviderBrand", () => {
  it("resolves a canonical id directly", () => {
    expect(getProviderBrand("openai").displayName).toBe("OpenAI");
  });

  it("resolves PROVIDER_CATALOG's shorter ids via alias", () => {
    expect(getProviderBrand("azure").displayName).toBe("Azure OpenAI");
    expect(getProviderBrand("xai").displayName).toBe("Grok (xAI)");
  });

  it("resolves OpenRouter's underlying-vendor slugs via alias", () => {
    expect(getProviderBrand("meta-llama").displayName).toBe("Meta Llama");
    expect(getProviderBrand("mistralai").displayName).toBe("Mistral");
  });

  it("is case-insensitive", () => {
    expect(getProviderBrand("OpenAI").displayName).toBe("OpenAI");
  });

  it("falls back to a generic, logo-less entry for an unknown id, never throwing", () => {
    const brand = getProviderBrand("some-future-vendor-nobody-has-heard-of");
    expect(brand.logo).toBe("");
    expect(brand.capabilities).toEqual([]);
    expect(brand.displayName).toBeTruthy();
  });
});

// EP-26.0.4 — ProviderLogo component
describe("ProviderLogo", () => {
  it("renders an accessible image with the provider's display name in the alt text", () => {
    render(<ProviderLogo providerId="anthropic" />);
    const img = screen.getByAltText("Anthropic logo");
    expect(img).toBeTruthy();
    expect(img.tagName).toBe("IMG");
  });

  it("renders the neutral chip wrapper with an aria-label by default", () => {
    render(<ProviderLogo providerId="openai" />);
    expect(screen.getByLabelText("OpenAI logo")).toBeTruthy();
  });

  it("omits the chip wrapper when bare is set", () => {
    const { container } = render(<ProviderLogo providerId="google" bare />);
    expect(container.querySelector(".bg-white\\/90")).toBeNull();
  });

  it("falls back to a generic icon (no <img>) for an unrecognized provider id", () => {
    const { container } = render(<ProviderLogo providerId="totally-unknown-provider" />);
    expect(container.querySelector("img")).toBeNull();
    // The lucide fallback icon still carries an accessible label.
    expect(screen.getByLabelText(/no logo available/i)).toBeTruthy();
  });

  it("applies the requested pixel size", () => {
    render(<ProviderLogo providerId="openai" size="lg" />);
    const chip = screen.getByLabelText("OpenAI logo");
    expect(chip.getAttribute("style")).toContain("40px");
  });
});
