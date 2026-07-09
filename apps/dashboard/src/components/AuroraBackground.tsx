import { cn } from "../utils";

interface AuroraBackgroundProps {
  className?: string;
}

/**
 * Slow-drifting multi-stop radial gradient mesh. GPU-accelerated
 * (transform + opacity only) via the `animate-aurora` keyframe.
 */
export default function AuroraBackground({ className }: AuroraBackgroundProps) {
  return (
    <div className={cn("absolute inset-0 overflow-hidden pointer-events-none", className)} aria-hidden="true">
      <div className="absolute inset-[-10%] bg-aurora animate-aurora" />
      <div className="absolute inset-0 bg-app-bg/40" />
    </div>
  );
}
