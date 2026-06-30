import { cn, providerDisplayName } from "../lib/utils";

const PROVIDER_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  openai:    { bg: "bg-openai-dim",    text: "text-openai",    dot: "bg-openai"    },
  anthropic: { bg: "bg-anthropic-dim", text: "text-anthropic", dot: "bg-anthropic" },
  google:    { bg: "bg-google-dim",    text: "text-google",    dot: "bg-google"    },
  azure:     { bg: "bg-azure-dim",     text: "text-azure",     dot: "bg-azure"     },
  bedrock:   { bg: "bg-bedrock-dim",   text: "text-bedrock",   dot: "bg-bedrock"   },
  cohere:    { bg: "bg-cohere-dim",    text: "text-cohere",    dot: "bg-cohere"    },
};

const FALLBACK = { bg: "bg-primary-subtle", text: "text-primary", dot: "bg-primary" };

interface ProviderBadgeProps {
  provider: string;
  size?: "sm" | "md";
  showDot?: boolean;
}

export default function ProviderBadge({ provider, size = "md", showDot = true }: ProviderBadgeProps) {
  const style = PROVIDER_STYLES[provider.toLowerCase()] ?? FALLBACK;
  return (
    <span
      className={cn(
        "badge",
        style.bg,
        style.text,
        size === "sm" && "text-[10px] px-1.5 py-0.5",
      )}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full", style.dot)} />}
      {providerDisplayName(provider)}
    </span>
  );
}

export function ProviderDot({ provider, size = 8 }: { provider: string; size?: number }) {
  const style = PROVIDER_STYLES[provider.toLowerCase()] ?? FALLBACK;
  return (
    <span
      className={cn("rounded-full inline-block flex-shrink-0", style.dot)}
      style={{ width: size, height: size }}
    />
  );
}

export const PROVIDER_COLORS: Record<string, string> = {
  openai:    "#10A37F",
  anthropic: "#D4A574",
  google:    "#4285F4",
  azure:     "#0078D4",
  bedrock:   "#FF9900",
  cohere:    "#9B5DE5",
};
