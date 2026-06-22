/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#2e7d5b",
          dark: "#1f5a40",
          light: "#e6f2ec",
        },
      },
    },
  },
  plugins: [],
};
