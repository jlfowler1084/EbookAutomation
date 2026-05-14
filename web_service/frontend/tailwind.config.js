/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  corePlugins: {
    preflight: false,   // CRITICAL: existing pages use inline styles only
  },
  theme: {
    extend: {
      colors: {
        brand:       "#1a1a2e",
        accent:      "#e8642c",
        muted:       "#6b7280",
        surface:     "#f9f7f4",
        border:      "#e5e7eb",
        "text-base": "#1f2937",
      },
      fontFamily: {
        sans:  ['"Inter", ui-sans-serif, system-ui, sans-serif'],
        serif: ['"Lora", ui-serif, Georgia, serif'],
      },
      boxShadow: {
        sm: "0 1px 3px 0 rgb(0 0 0 / 0.08)",
        md: "0 4px 12px 0 rgb(0 0 0 / 0.10)",
        lg: "0 8px 24px 0 rgb(0 0 0 / 0.12)",
      },
      borderRadius: {
        sm: "0.25rem",
        md: "0.5rem",
      },
    },
  },
  plugins: [],
};
