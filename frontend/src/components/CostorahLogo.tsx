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
      {/* Trailing accent chevrons — decreasing size, parallel to the main spine */}
      <path d="M28 46 L36 38 L36 46 L28 54 Z" fill="currentColor" />
      <path d="M18 54 L25 47 L25 54 L18 61 Z" fill="currentColor" opacity="0.75" />
      <path d="M10 61 L16 55 L16 61 L10 67 Z" fill="currentColor" opacity="0.5" />
      {/* Angular arrow body — top spike + two lower wings */}
      <path
        d="M72 15 L76 29 L63 33 L78 42 L90 80 L58 58 L12 92 L46 54 L28 52 Z"
        fill="currentColor"
      />
      {/* "C" cut-through */}
      <circle cx="58" cy="44" r="15" fill="#0A0A0F" />
      <path
        d="M65.3 36.5a10.5 10.5 0 1 0 0 15"
        stroke="currentColor"
        strokeWidth="7"
        strokeLinecap="butt"
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
        <div className="text-[10px] font-medium tracking-[0.2em] text-tx-secondary uppercase mt-0.5">
          Track. Analyze. Optimize AI Costs.
        </div>
      </div>
    </div>
  );
}
