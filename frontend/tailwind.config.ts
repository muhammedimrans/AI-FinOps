import type { Config } from "tailwindcss";

/**
 * Resolves a Tailwind color to a runtime CSS variable so it can change per-theme without a rebuild.
 * Tailwind's JS API accepts a function here at runtime (it calls it with `{ opacityValue }` for
 * `bg-brand/50`-style modifiers), but its published types only declare `string`, so the return
 * value is cast to match — this is a type-level lie, not a behavior change.
 */
function themed(variable: string): string {
  return ((({ opacityValue }: { opacityValue?: string }) =>
    opacityValue === undefined ? `rgb(var(${variable}))` : `rgb(var(${variable}) / ${opacityValue})`) as unknown) as string;
}

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // App backgrounds
        app: {
          bg: themed("--color-app-bg"),
          card: themed("--color-app-card"),
          muted: themed("--color-app-muted"),
          hover: themed("--color-app-hover"),
        },
        // Secondary accent (legacy "primary" — indigo/purple family, theme-mapped)
        primary: {
          DEFAULT: themed("--color-primary"),
          hover: themed("--color-primary-hover"),
          light: themed("--color-primary-light"),
          dim: themed("--color-primary-dim"),
          subtle: `rgb(var(--color-primary) / 0.12)`,
        },
        // Costorah brand — the app's primary accent, remapped per theme
        brand: {
          DEFAULT: themed("--color-brand"),
          hover: themed("--color-brand-hover"),
          light: themed("--color-brand-light"),
          dim: themed("--color-brand-dim"),
          subtle: `rgb(var(--color-brand) / 0.12)`,
          purple: themed("--color-brand-purple"),
        },
        // Semantic
        success: { DEFAULT: themed("--color-success"), dim: `rgb(var(--color-success) / 0.12)`, light: themed("--color-success-light") },
        warning: { DEFAULT: themed("--color-warning"), dim: `rgb(var(--color-warning) / 0.12)`, light: themed("--color-warning-light") },
        danger:  { DEFAULT: themed("--color-danger"),  dim: `rgb(var(--color-danger) / 0.12)`,  light: themed("--color-danger-light") },
        info:    { DEFAULT: themed("--color-info"),    dim: `rgb(var(--color-info) / 0.12)`,    light: themed("--color-info-light") },
        // Text
        tx: {
          primary:   themed("--color-tx-primary"),
          secondary: themed("--color-tx-secondary"),
          muted:     themed("--color-tx-muted"),
          disabled:  themed("--color-tx-disabled"),
        },
        // Borders
        border: {
          subtle:  themed("--color-border-subtle"),
          DEFAULT: themed("--color-border"),
          strong:  themed("--color-border-strong"),
        },
        // Provider colors — third-party brand identity, constant across themes
        openai:    { DEFAULT: "#10A37F", dim: "rgba(16,163,127,0.15)" },
        anthropic: { DEFAULT: "#D4A574", dim: "rgba(212,165,116,0.15)" },
        google:    { DEFAULT: "#4285F4", dim: "rgba(66,133,244,0.15)" },
        azure:     { DEFAULT: "#0078D4", dim: "rgba(0,120,212,0.15)" },
        bedrock:   { DEFAULT: "#FF9900", dim: "rgba(255,153,0,0.15)" },
        cohere:    { DEFAULT: "#9B5DE5", dim: "rgba(155,93,229,0.15)" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      fontSize: {
        "display": ["48px", { lineHeight: "1.1", fontWeight: "700" }],
        "h1":      ["36px", { lineHeight: "1.2", fontWeight: "700" }],
        "h2":      ["28px", { lineHeight: "1.3", fontWeight: "600" }],
        "h3":      ["22px", { lineHeight: "1.4", fontWeight: "600" }],
        "h4":      ["18px", { lineHeight: "1.5", fontWeight: "600" }],
      },
      borderRadius: {
        card: "12px",
        "card-lg": "20px",
        "card-xl": "28px",
        lg:   "8px",
        md:   "6px",
        sm:   "4px",
      },
      boxShadow: {
        card:    "0 1px 3px rgb(var(--shadow-rgb) / var(--shadow-a-1)), 0 1px 2px rgb(var(--shadow-rgb) / var(--shadow-a-2))",
        "card-hover": "0 4px 12px rgb(var(--shadow-rgb) / var(--shadow-a-3)), 0 2px 4px rgb(var(--shadow-rgb) / var(--shadow-a-2))",
        "glow-brand": "0 0 32px rgb(var(--color-brand) / var(--glow-a))",
        "glow-brand-lg": "0 0 60px rgb(var(--color-brand) / var(--glow-a-lg)), 0 0 120px rgb(var(--color-brand-purple) / var(--glow-a-sm))",
        elevated: "0 8px 24px rgb(var(--shadow-rgb) / var(--shadow-a-4)), 0 2px 8px rgb(var(--shadow-rgb) / var(--shadow-a-3)), 0 0 0 1px rgb(var(--glass-edge-rgb) / var(--glass-edge-a))",
      },
      backgroundImage: {
        "gradient-brand":   "linear-gradient(135deg, rgb(var(--color-brand)) 0%, rgb(var(--color-brand-hover)) 100%)",
        "gradient-brand-radial": "radial-gradient(ellipse at top left, rgb(var(--color-brand) / var(--glow-a-lg)) 0%, rgb(var(--color-brand-purple) / var(--glow-a-sm)) 45%, rgb(var(--color-app-bg) / 0) 75%)",
        aurora: "radial-gradient(ellipse 80% 50% at 20% 0%, rgb(var(--color-brand) / var(--aurora-a)) 0%, transparent 60%), " +
                "radial-gradient(ellipse 60% 50% at 80% 10%, rgb(var(--color-brand-purple) / var(--aurora-a-2)) 0%, transparent 60%), " +
                "radial-gradient(ellipse 70% 60% at 50% 100%, rgb(var(--color-brand) / var(--aurora-a-3)) 0%, transparent 60%)",
      },
      animation: {
        "fade-in": "fadeIn 0.2s ease-out",
        float: "float 6s ease-in-out infinite",
        "float-slow": "float 9s ease-in-out infinite",
        "glow-pulse": "glowPulse 4s ease-in-out infinite",
        aurora: "auroraShift 18s ease-in-out infinite",
        drift: "drift 14s linear infinite",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        float: {
          "0%, 100%": { transform: "translate3d(0, 0, 0)" },
          "50%": { transform: "translate3d(0, -14px, 0)" },
        },
        glowPulse: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        auroraShift: {
          "0%, 100%": { transform: "translate3d(0, 0, 0) scale(1)" },
          "50%": { transform: "translate3d(2%, -2%, 0) scale(1.05)" },
        },
        drift: {
          "0%": { transform: "translate3d(0, 100%, 0)", opacity: "0" },
          "10%": { opacity: "0.7" },
          "50%": { transform: "translate3d(var(--drift-x, 20px), 40%, 0)" },
          "90%": { opacity: "0.7" },
          "100%": { transform: "translate3d(0, -20%, 0)", opacity: "0" },
        },
      },
      transitionDuration: {
        fast: "150ms",
        base: "200ms",
        slow: "300ms",
      },
    },
  },
  plugins: [],
};

export default config;
