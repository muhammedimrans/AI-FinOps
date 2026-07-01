import { useMemo, type CSSProperties } from "react";

interface ParticleFieldProps {
  count?: number;
  className?: string;
}

interface Particle {
  left: number;
  size: number;
  duration: number;
  delay: number;
  drift: number;
}

/** CSSProperties plus the custom property consumed by the `drift` keyframe. */
type ParticleStyle = CSSProperties & { "--drift-x"?: string };

/**
 * Ambient floating-particle backdrop. Pure CSS transform/opacity animation
 * (GPU-accelerated, no per-frame JS) — safe to layer behind any hero surface.
 */
export default function ParticleField({ count = 24, className }: ParticleFieldProps) {
  const particles = useMemo<Particle[]>(
    () =>
      Array.from({ length: count }, () => ({
        left: Math.random() * 100,
        size: 2 + Math.random() * 3,
        duration: 10 + Math.random() * 10,
        delay: Math.random() * -20,
        drift: (Math.random() - 0.5) * 40,
      })),
    [count],
  );

  return (
    <div className={className} aria-hidden="true">
      {particles.map((p, i) => {
        const style: ParticleStyle = {
          left: `${p.left}%`,
          bottom: 0,
          width: p.size,
          height: p.size,
          animationDuration: `${p.duration}s`,
          animationDelay: `${p.delay}s`,
          filter: "blur(0.5px)",
          boxShadow: "0 0 6px rgb(var(--color-brand) / 0.6)",
          "--drift-x": `${p.drift}px`,
        };
        return (
          <span
            key={i}
            className="absolute rounded-full bg-brand animate-drift"
            style={style}
          />
        );
      })}
    </div>
  );
}
