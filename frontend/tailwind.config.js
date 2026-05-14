/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b1020",
        panel: "#131a30",
        accent: "#6ee7f9",
        danger: "#ef4444",
        warn: "#f59e0b",
        ok: "#22c55e",
      },
    },
  },
  plugins: [],
};
