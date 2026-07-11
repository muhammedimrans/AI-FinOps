/**
 * Costorah brand mark — the official logo artwork (src/assets/Costorah.png,
 * provided by the product team). `variant="mark"` renders the glyph only
 * (sidebar, favicon-style contexts); `variant="full"` adds the wordmark +
 * tagline (login, splash contexts).
 */
import { cn } from "../utils";
import markSrc from "../assets/Costorah.png";

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
