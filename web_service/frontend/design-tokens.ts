export const colors = {
  brand:    "#1a1a2e",
  accent:   "#e8642c",
  muted:    "#6b7280",
  surface:  "#f9f7f4",
  border:   "#e5e7eb",
  textBase: "#1f2937",
} as const;

export const type = {
  fontSans: '"Inter", ui-sans-serif, system-ui, sans-serif',
  fontSerif: '"Lora", ui-serif, Georgia, serif',
  // Modular scale: 12/14/16/20/24/32/48
  scaleXs:  "0.75rem",
  scaleSm:  "0.875rem",
  scaleMd:  "1rem",
  scaleLg:  "1.25rem",
  scaleXl:  "1.5rem",
  scale2Xl: "2rem",
  scale3Xl: "3rem",
} as const;

export const space = {
  // 4-point base: 4/8/12/16/24/32/48/64
  1: "0.25rem", 2: "0.5rem", 3: "0.75rem",
  4: "1rem",   6: "1.5rem", 8: "2rem",
  12: "3rem",  16: "4rem",
} as const;

export const shadows = {
  sm:  "0 1px 3px 0 rgb(0 0 0 / 0.08)",
  md:  "0 4px 12px 0 rgb(0 0 0 / 0.10)",
  lg:  "0 8px 24px 0 rgb(0 0 0 / 0.12)",
} as const;

export const radii = {
  sm: "0.25rem",
  md: "0.5rem",
} as const;
