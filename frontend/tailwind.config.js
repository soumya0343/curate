/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#FAF9F7",
        primary: "#121212",
        gold: {
          50:  "#FDF8EE",
          100: "#F9EDD0",
          200: "#F2D9A0",
          300: "#E8C068",
          400: "#D4A843",
          500: "#B8892A",
        },
      },
      fontFamily: {
        serif: ["EB Garamond", "Georgia", "serif"],
        sans:  ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
