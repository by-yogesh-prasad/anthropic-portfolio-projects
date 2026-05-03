/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        anthropic: {
          orange: "#D97757",
          dark: "#1A1A1A",
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
