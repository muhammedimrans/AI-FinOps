/**
 * Costorah brand mark — teal arrow/flag "C" glyph, recreated as inline SVG.
 * `variant="mark"` renders the glyph only (sidebar, favicon-style contexts);
 * `variant="full"` adds the wordmark + tagline (login screen, splash contexts).
 */
import { cn } from "../lib/utils";

interface CostorahLogoProps {
  variant?: "mark" | "full";
  className?: string;
  markClassName?: string;
}

export function CostorahMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("text-brand", className)}
      role="img"
      aria-label="Costorah"
    >
      {/* Trailing accent chevrons */}
      <path d="M30 40 L38 32 L38 40 L30 48 Z" fill="currentColor" opacity="0.55" />
      <path d="M20 48 L28 40 L28 48 L20 56 Z" fill="currentColor" opacity="0.35" />
      {/* Angular flag / arrow body */}
      <path
        d="M88 6 L44 50 L54 50 L14 78 L48 66 L10 94 L74 58 L62 58 L92 30 Z"
        fill="currentColor"
      />
      {/* "C" cut-through */}
      <circle cx="55" cy="62" r="15" fill="#05070A" />
      <path
        d="M62 54a10.5 10.5 0 1 0 0 16"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

export default function CostorahLogo({ variant = "full", className, markClassName }: CostorahLogoProps) {
  if (variant === "mark") {
    return <CostorahMark className={cn("w-9 h-9", markClassName)} />;
  }

  return (
    <div className={cn("flex flex-col items-center gap-2", className)}>
      <CostorahMark className={cn("w-14 h-14", markClassName)} />
      <div className="text-center">
        <div className="text-xl font-bold tracking-[0.15em] text-tx-primary">COSTORAH</div>
        <div className="text-[10px] font-medium tracking-[0.2em] text-tx-muted uppercase mt-0.5">
          Track. Analyze. Optimize AI Costs.
        </div>
      </div>
    </div>
  );
}
