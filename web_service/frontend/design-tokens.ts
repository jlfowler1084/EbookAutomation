/**
 * leafbind visual tokens — source of truth.
 *
 * - tailwind.config.ts imports these named exports.
 * - app/globals.css `:root` mirrors these hex values via --color-* variables.
 * - tools/check-token-drift.mjs verifies the two stay in sync.
 *
 * Run `npm run check:tokens` after any edit here; this script runs automatically
 * as part of `prebuild`.
 */
export const colors = {
  brand:        "#2D4A2B",
  brandDark:    "#1a3a1a",
  accent:       "#3D7A3A",
  surface:      "#FAF8F3",
  surfaceMuted: "#F5F1E8",
  border:       "#E2DFD5",
  textBase:     "#1a1a1a",
  textMuted:    "#6a6a6a",
} as const;

export const type = {
  fontSans:  "var(--font-inter), ui-sans-serif, system-ui, sans-serif",
  fontSerif: "var(--font-lora), ui-serif, Georgia, serif",
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
