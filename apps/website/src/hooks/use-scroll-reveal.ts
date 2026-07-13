import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface ScrollRevealOptions {
  /** CSS selector, scoped to the container ref, for the elements to reveal. */
  selector: string;
  /** Pixels to rise from on entry. */
  y?: number;
  /** Seconds per element. */
  duration?: number;
  /** Seconds of stagger between elements. */
  stagger?: number;
  /** Delay before the reveal starts, once triggered. */
  delay?: number;
}

/**
 * Reveals `selector` matches inside the returned ref with a GSAP
 * ScrollTrigger-driven fade + rise, once, the first time the container
 * enters the viewport. Honors `prefers-reduced-motion` (renders the final
 * state immediately, no animation). Every ScrollTrigger instance this hook
 * creates is killed on unmount/re-run, which matters in a SPA where route
 * changes can otherwise leak stale scroll listeners.
 *
 * This is deliberately narrow — one reusable primitive for "reveal these
 * elements as they scroll into view," reused across every static landing
 * page section, rather than one-off GSAP timelines per section.
 */
export function useScrollReveal<T extends HTMLElement = HTMLDivElement>({
  selector,
  y = 24,
  duration = 0.7,
  stagger = 0.08,
  delay = 0,
}: ScrollRevealOptions) {
  const containerRef = useRef<T | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const targets = container.querySelectorAll<HTMLElement>(selector);
    if (targets.length === 0) return;

    if (prefersReducedMotion()) {
      gsap.set(targets, { opacity: 1, y: 0 });
      return;
    }

    const ctx = gsap.context(() => {
      gsap.set(targets, { opacity: 0, y });
      gsap.to(targets, {
        opacity: 1,
        y: 0,
        duration,
        delay,
        stagger,
        ease: "power2.out",
        scrollTrigger: {
          trigger: container,
          start: "top 85%",
          once: true,
        },
      });
    }, container);

    return () => ctx.revert();
  }, [selector, y, duration, stagger, delay]);

  return containerRef;
}
