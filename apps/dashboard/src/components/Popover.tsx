import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";

interface PopoverProps {
  /** Trigger element the popover is anchored to. */
  anchorRef: RefObject<HTMLElement>;
  open: boolean;
  onClose: () => void;
  /** Horizontal alignment relative to the anchor's edge. */
  align?: "start" | "end";
  className?: string;
  children: ReactNode;
}

interface Coords {
  top: number;
  left?: number;
  right?: number;
}

/**
 * Portals its content to document.body and positions it with `position: fixed`
 * against the anchor's live bounding rect. This sidesteps a real bug where a
 * CSS-stacking-context-creating ancestor (e.g. the header's backdrop-blur)
 * caused a later DOM sibling (`<main>`) to sit above an `absolute`-positioned
 * dropdown for pointer-event purposes — the dropdown was visible but clicks
 * on it were swallowed by whatever sat "on top" in the stacking order.
 * Also owns click-outside/Escape handling so every popover in the app closes
 * the same way regardless of where its content lives in the DOM.
 */
export default function Popover({ anchorRef, open, onClose, align = "end", className, children }: PopoverProps) {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [mounted, setMounted] = useState(open);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) setMounted(true);
  }, [open]);

  useLayoutEffect(() => {
    if (!mounted) return;
    function update() {
      const anchor = anchorRef.current;
      if (!anchor) return;
      const rect = anchor.getBoundingClientRect();
      setCoords(
        align === "end"
          ? { top: rect.bottom + 8, right: Math.max(8, window.innerWidth - rect.right) }
          : { top: rect.bottom + 8, left: rect.left },
      );
    }
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [mounted, anchorRef, align]);

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(e: MouseEvent) {
      const target = e.target as Node;
      if (anchorRef.current?.contains(target)) return;
      if (contentRef.current?.contains(target)) return;
      onClose();
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        anchorRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose, anchorRef]);

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence onExitComplete={() => setMounted(false)}>
      {open && coords && (
        <motion.div
          ref={contentRef}
          initial={{ opacity: 0, y: -4, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -4, scale: 0.97 }}
          transition={{ duration: 0.15, ease: "easeOut" }}
          style={{
            position: "fixed",
            top: coords.top,
            ...(coords.left !== undefined ? { left: coords.left } : {}),
            ...(coords.right !== undefined ? { right: coords.right } : {}),
          }}
          className={className}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
