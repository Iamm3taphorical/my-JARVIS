import type { Config } from "tailwindcss"

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "rgb(var(--surface) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        signal: "rgb(var(--signal) / <alpha-value>)",
        amberline: "rgb(var(--amberline) / <alpha-value>)",
      },
      boxShadow: {
        glass: "0 24px 80px rgba(0, 0, 0, 0.35)",
        signal: "0 0 40px rgba(65, 173, 255, 0.28)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(18px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        scan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        rise: "rise 700ms cubic-bezier(.2,.8,.2,1) both",
        scan: "scan 2.4s linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config
