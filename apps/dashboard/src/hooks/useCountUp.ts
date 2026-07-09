import { useEffect, useRef, useState } from "react";

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * Animates a numeric display value toward `target` using requestAnimationFrame
 * with an ease-out curve. Skips animation entirely under prefers-reduced-motion.
 */
export function useCountUp(target: number, duration = 800): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(0);
  const firstRun = useRef(true);

  useEffect(() => {
    if (!Number.isFinite(target)) {
      setValue(target);
      return;
    }
    if (firstRun.current) {
      // Animate in from 0 on first mount so cards feel alive on load.
      firstRun.current = false;
    }
    if (prefersReducedMotion()) {
      setValue(target);
      fromRef.current = target;
      return;
    }

    const from = fromRef.current;
    const startTime = performance.now();
    let raf: number;

    function tick(now: number) {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      const eased = 1 - (1 - t) ** 3; // easeOutCubic
      setValue(from + (target - from) * eased);
      if (t < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
      }
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return value;
}
