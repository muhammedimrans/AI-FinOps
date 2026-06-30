import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // App backgrounds
        app: {
          bg: "#0A0A0F",
          card: "#12121A",
          muted: "#1A1A26",
          hover: "#1E1E2E",
        },
        // Primary - Deep Indigo
        primary: {
          DEFAULT: "#4F46E5",
          hover: "#4338CA",
          light: "#6366F1",
          dim: "#312E81",
          subtle: "rgba(79,70,229,0.12)",
        },
        // Semantic
        success: { DEFAULT: "#10B981", dim: "rgba(16,185,129,0.12)", light: "#34D399" },
        warning: { DEFAULT: "#F59E0B", dim: "rgba(245,158,11,0.12)", light: "#FCD34D" },
        danger:  { DEFAULT: "#EF4444", dim: "rgba(239,68,68,0.12)",  light: "#F87171" },
        info:    { DEFAULT: "#3B82F6", dim: "rgba(59,130,246,0.12)", light: "#60A5FA" },
        // Text
        tx: {
          primary:   "#F8FAFC",
          secondary: "#94A3B8",
          muted:     "#475569",
          disabled:  "#334155",
        },
        // Borders
        border: {
          subtle:  "#1E293B",
          DEFAULT: "#334155",
          strong:  "#475569",
        },
        // Provider colors
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
        lg:   "8px",
        md:   "6px",
        sm:   "4px",
      },
      boxShadow: {
        card:    "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3)",
        glow:    "0 0 20px rgba(79,70,229,0.3)",
        "glow-success": "0 0 20px rgba(16,185,129,0.25)",
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)",
        "gradient-success": "linear-gradient(135deg, #10B981 0%, #059669 100%)",
        "gradient-card":    "linear-gradient(145deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%)",
        "gradient-shimmer": "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%)",
      },
      animation: {
        shimmer: "shimmer 1.5s infinite",
        "count-up": "countUp 0.8s ease-out",
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.25s ease-out",
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
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
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
