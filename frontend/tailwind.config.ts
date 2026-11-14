import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "lunar-dark":    "#0a0c14",
        "lunar-panel":   "#111827",
        "lunar-border":  "#1f2d4a",
        "lunar-accent":  "#3b82f6",
        "solar-gold":    "#f59e0b",
        "earth-cyan":    "#06b6d4",
        "alert-red":     "#ef4444",
        "go-green":      "#22c55e",
        "caution-amber": "#f59e0b",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "'Fira Code'", "monospace"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
      },
      backdropBlur: {
        xs: "2px",
      },
      animation: {
        "pulse-slow":    "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "spin-slow":     "spin 8s linear infinite",
        "radar-sweep":   "radar-sweep 2s linear infinite",
        "fade-in":       "fadeIn 0.4s ease-out",
        "slide-up":      "slideUp 0.3s ease-out",
      },
      keyframes: {
        "radar-sweep": {
          "0%":   { transform: "rotate(0deg)", opacity: "0.9" },
          "100%": { transform: "rotate(360deg)", opacity: "0.9" },
        },
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
