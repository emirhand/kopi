/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      keyframes: {
        "kopi-shimmer": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "kopi-shimmer": "kopi-shimmer 1.4s ease-in-out infinite",
      },
      colors: {
        kiosk: {
          bg: "#0a0a0b",
          panel: "#141416",
          accent: "#3b82f6",
          accent2: "#22c55e",
          warn: "#f59e0b",
          danger: "#ef4444",
          text: "#f4f4f5",
          muted: "#a1a1aa",
          industrial: {
            navy: "#0f172a",
            slate: "#1e293b",
            border: "#334155",
            bezel: "#0c1222",
          },
        },
      },
      fontFamily: {
        kiosk: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
