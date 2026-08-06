/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        app: "#FAFAFA",
        ink: { DEFAULT: "#09090B", soft: "#52525B", faint: "#A1A1AA" },
        line: "#E4E4E7",
        cobalt: { DEFAULT: "#1D4ED8", hover: "#1E40AF", active: "#1E3A8A", tint: "#EFF4FF" },
      },
      fontFamily: {
        heading: ["Cabinet Grotesk", "system-ui", "sans-serif"],
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(9,9,11,0.04), 0 1px 3px 0 rgba(9,9,11,0.06)",
        drawer: "-8px 0 40px -12px rgba(9,9,11,0.18)",
      },
      keyframes: {
        "fade-up": { "0%": { opacity: 0, transform: "translateY(6px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
        "drawer-in": { "0%": { transform: "translateX(100%)" }, "100%": { transform: "translateX(0)" } },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        "drawer-in": "drawer-in 0.3s cubic-bezier(0.32,0.72,0,1) both",
      },
    },
  },
  plugins: [],
};
