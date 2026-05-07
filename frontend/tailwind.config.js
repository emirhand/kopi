/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
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
        },
      },
      fontFamily: {
        kiosk: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
