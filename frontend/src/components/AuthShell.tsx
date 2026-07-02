import type { ReactNode } from "react";
import { motion } from "framer-motion";
import AuroraBackground from "./AuroraBackground";
import ParticleField from "./ParticleField";
import ThemeSwitcher from "./ThemeSwitcher";
import { CostorahMark } from "./CostorahLogo";

/**
 * Centered single-panel layout for auxiliary auth pages (password reset,
 * email verification) — same ambient background language as Login without
 * the marketing split-screen.
 */
export default function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen w-full flex items-center justify-center relative bg-app-bg overflow-hidden p-4">
      <AuroraBackground />
      <ParticleField count={20} className="absolute inset-0 z-0" />
      <div className="absolute top-4 right-4 z-20">
        <ThemeSwitcher />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="w-full max-w-md relative z-10"
      >
        <div className="absolute -inset-8 bg-gradient-brand-radial blur-3xl opacity-50 pointer-events-none" aria-hidden="true" />
        <div className="glass-panel shadow-glow-brand-lg p-8 sm:p-10 relative">
          <div className="flex items-center gap-2.5 mb-8">
            <CostorahMark className="w-8 h-8" />
            <span className="font-display text-sm font-bold tracking-[0.12em] text-tx-primary">COSTORAH</span>
          </div>
          {children}
        </div>
      </motion.div>
    </div>
  );
}
