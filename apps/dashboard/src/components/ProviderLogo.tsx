import { Box } from "lucide-react";
import { getProviderBrand } from "../lib/providerCatalog";
import { cn } from "../utils";

// EP-26.0.4 — the one component every page renders a provider's actual
// brand mark through. Never imports a provider SVG directly (that only
// happens once, in lib/providerCatalog.ts's registry) — every consumer
// goes through `getProviderBrand()` so there is exactly one lookup, exactly
// one set of imported assets, no matter how many places show a logo.
//
// Dark mode: the chip's background is a fixed, theme-independent
// near-white (`bg-white/90`) rather than following the page's own
// `data-theme` tokens — several brand marks (Anthropic, Ollama) are
// near-black and would disappear on a dark card background if rendered
// bare. This is the same "logo badge chip on a neutral background" pattern
// most SaaS integration pages use (Zapier, Notion, n8n, etc.), and it's
// the reason logos stay legible and true-to-brand-color in every theme
// without needing a second, re-tinted asset per provider.
const SIZE_PX: Record<NonNullable<ProviderLogoProps["size"]>, number> = {
  xs: 16,
  sm: 20,
  md: 28,
  lg: 40,
};

interface ProviderLogoProps {
  providerId: string;
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
  /** Render without the neutral chip background — for placement on an
   * already-neutral surface (e.g. inside a table cell next to text). */
  bare?: boolean;
}

export default function ProviderLogo({
  providerId,
  size = "md",
  className,
  bare = false,
}: ProviderLogoProps) {
  const brand = getProviderBrand(providerId);
  const px = SIZE_PX[size];
  const iconPx = bare ? px : Math.round(px * 0.62);

  const content = brand.logo ? (
    <img
      src={brand.logo}
      alt={`${brand.displayName} logo`}
      width={iconPx}
      height={iconPx}
      style={{ width: iconPx, height: iconPx }}
      className="block object-contain"
      loading="lazy"
      decoding="async"
    />
  ) : (
    <Box
      role="img"
      aria-label={`${brand.displayName} (no logo available)`}
      width={iconPx}
      height={iconPx}
      className="text-tx-muted"
    />
  );

  if (bare) {
    return (
      <span className={cn("inline-flex items-center justify-center flex-shrink-0", className)}>
        {content}
      </span>
    );
  }

  return (
    <span
      role="img"
      aria-label={`${brand.displayName} logo`}
      className={cn(
        "inline-flex items-center justify-center flex-shrink-0 rounded-md bg-white/90 ring-1 ring-black/5",
        className,
      )}
      style={{ width: px, height: px }}
    >
      {content}
    </span>
  );
}
