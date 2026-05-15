#!/usr/bin/env node
/**
 * Token drift guard for EB-233/EB-248 design system.
 *
 * Validates color tokens across three surfaces:
 *   1. design-tokens.ts  ←→  globals.css :root  (Next.js CSS variables)
 *   2. design-tokens.ts  ←→  leafbind-tokens.css :root  (FastAPI brand CSS, EB-248)
 *
 * Exits 1 on any drift with a specific diff report.
 * Runs as part of `prebuild` after gen-fastapi-css.mjs so the generated CSS
 * is validated before any Vercel deploy or FastAPI deploy.
 */
import { readFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const webServiceRoot = path.resolve(root, "..");

const tokensSrc = await readFile(path.join(root, "design-tokens.ts"), "utf-8");
const globalsSrc = await readFile(path.join(root, "app", "globals.css"), "utf-8");
const fastapiCssSrc = await readFile(
  path.join(webServiceRoot, "static", "leafbind-tokens.css"),
  "utf-8"
);

// ── helpers ──────────────────────────────────────────────────────────────────

function extractTsColors(src) {
  const colorsBlockMatch = src.match(/export\s+const\s+colors\s*=\s*\{([\s\S]*?)\}\s*as\s+const/);
  if (!colorsBlockMatch) {
    console.error("ERROR: could not locate `export const colors = { ... } as const` in design-tokens.ts");
    process.exit(1);
  }
  const tokens = new Map();
  for (const line of colorsBlockMatch[1].split("\n")) {
    const m = line.match(/^\s*([a-zA-Z][a-zA-Z0-9]*|"[a-z-]+"|'[a-z-]+')\s*:\s*["']?(#[0-9a-fA-F]{3,8})["']?/);
    if (m) {
      const key = m[1].replace(/['"]/g, "");
      const kebabKey = key.replace(/([A-Z])/g, "-$1").toLowerCase();
      tokens.set(kebabKey, m[2].toLowerCase());
    }
  }
  return tokens;
}

function extractCssColorVars(src) {
  const tokens = new Map();
  const re = /--color-([a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,8})/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    tokens.set(m[1], m[2].toLowerCase());
  }
  return tokens;
}

function diffColorMaps(tsTokens, cssTokens, cssLabel) {
  let drift = false;
  const tsKeys = new Set(tsTokens.keys());
  const cssKeys = new Set(cssTokens.keys());
  for (const k of tsKeys) {
    if (!cssKeys.has(k)) {
      console.error(`DRIFT [${cssLabel}]: design-tokens.ts defines '${k}' (${tsTokens.get(k)}) but ${cssLabel} has no --color-${k}`);
      drift = true;
    } else if (tsTokens.get(k) !== cssTokens.get(k)) {
      console.error(`DRIFT [${cssLabel}]: '${k}' is ${tsTokens.get(k)} in design-tokens.ts but ${cssTokens.get(k)} in ${cssLabel}`);
      drift = true;
    }
  }
  for (const k of cssKeys) {
    if (!tsKeys.has(k)) {
      console.error(`DRIFT [${cssLabel}]: ${cssLabel} has --color-${k} (${cssTokens.get(k)}) but design-tokens.ts has no matching key`);
      drift = true;
    }
  }
  return drift;
}

// ── Run checks ───────────────────────────────────────────────────────────────

const tsTokens = extractTsColors(tokensSrc);
const globalsTokens = extractCssColorVars(globalsSrc);
const fastapiTokens = extractCssColorVars(fastapiCssSrc);

let anyDrift = false;

anyDrift = diffColorMaps(tsTokens, globalsTokens, "globals.css") || anyDrift;
anyDrift = diffColorMaps(tsTokens, fastapiTokens, "leafbind-tokens.css") || anyDrift;

if (anyDrift) {
  console.error("\nFAIL: token drift detected. Fix by aligning all three files. design-tokens.ts is source of truth.");
  console.error("Regenerate leafbind-tokens.css: node web_service/frontend/tools/gen-fastapi-css.mjs");
  process.exit(1);
}

console.log(`OK: ${tsTokens.size} color tokens in design-tokens.ts match globals.css :root and leafbind-tokens.css :root.`);
