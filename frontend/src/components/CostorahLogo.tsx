/**
 * Costorah brand mark — the actual logo artwork (src/assets/costorah-mark.png),
 * cropped and alpha-keyed from the source lockup so it drops in transparently
 * at any size. `variant="mark"` renders the glyph only (sidebar, favicon-style
 * contexts); `variant="full"` adds the wordmark + tagline (login, splash contexts).
 */
import { cn } from "../lib/utils";
import markSrc from "../assets/costorah-mark.png";

interface CostorahLogoProps {
  variant?: "mark" | "full";
  className?: string;
  markClassName?: string;
}

export function CostorahMark({ className }: { className?: string }) {
  return (
    <img
      src={markSrc}
      alt="Costorah"
      className={cn("object-contain", className)}
    />
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
