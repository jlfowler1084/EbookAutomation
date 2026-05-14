#!/usr/bin/env node
/**
 * Token drift guard for EB-233 design system.
 *
 * Verifies that design-tokens.ts `colors` export and globals.css `:root` block
 * define the same key set with the same hex values. Exits 1 on drift with a
 * specific diff report.
 *
 * Runs as part of `prebuild` so CI fails before any Vercel deploy that has
 * drifted tokens.
 */
import { readFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

const tokensSrc = await readFile(path.join(root, "design-tokens.ts"), "utf-8");
const globalsSrc = await readFile(path.join(root, "app", "globals.css"), "utf-8");

// Extract colors object from design-tokens.ts
const colorsBlockMatch = tokensSrc.match(/export\s+const\s+colors\s*=\s*\{([\s\S]*?)\}\s*as\s+const/);
if (!colorsBlockMatch) {
  console.error("ERROR: could not locate `export const colors = { ... } as const` in design-tokens.ts");
  process.exit(1);
}
const tsTokens = new Map();
for (const line of colorsBlockMatch[1].split("\n")) {
  const m = line.match(/^\s*([a-zA-Z][a-zA-Z0-9]*|"[a-z-]+"|'[a-z-]+')\s*:\s*["']?(#[0-9a-fA-F]{3,8})["']?/);
  if (m) {
    const key = m[1].replace(/['"]/g, "");
    // Convert camelCase to kebab-case for comparison with CSS vars
    const kebabKey = key.replace(/([A-Z])/g, "-$1").toLowerCase();
    tsTokens.set(kebabKey, m[2].toLowerCase());
  }
}

// Extract :root --color-* declarations from globals.css
const cssTokens = new Map();
const cssVarRegex = /--color-([a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,8})/g;
let m;
while ((m = cssVarRegex.exec(globalsSrc)) !== null) {
  cssTokens.set(m[1], m[2].toLowerCase());
}

// Diff
let drift = false;
const tsKeys = new Set(tsTokens.keys());
const cssKeys = new Set(cssTokens.keys());

for (const k of tsKeys) {
  if (!cssKeys.has(k)) {
    console.error(`DRIFT: design-tokens.ts defines '${k}' (${tsTokens.get(k)}) but globals.css :root has no --color-${k}`);
    drift = true;
  } else if (tsTokens.get(k) !== cssTokens.get(k)) {
    console.error(`DRIFT: '${k}' is ${tsTokens.get(k)} in design-tokens.ts but ${cssTokens.get(k)} in globals.css`);
    drift = true;
  }
}
for (const k of cssKeys) {
  if (!tsKeys.has(k)) {
    console.error(`DRIFT: globals.css :root has --color-${k} (${cssTokens.get(k)}) but design-tokens.ts has no matching key`);
    drift = true;
  }
}

if (drift) {
  console.error("\nFAIL: token drift detected between design-tokens.ts and globals.css :root.");
  console.error("Fix by aligning the two files. design-tokens.ts is source of truth.");
  process.exit(1);
}
console.log(`OK: ${tsKeys.size} tokens in design-tokens.ts <-> globals.css :root all match.`);
