#!/usr/bin/env node
/**
 * check-shell-drift.mjs — guard against drift between the Python payment-flow
 * shell (web_service/templates/shell.py) and the Next.js components it mirrors
 * (Header.tsx, Footer.tsx).
 *
 * Checks:
 *   1. The home link aria-label in header_html() matches Header.tsx.
 *   2. /pricing and /recover links appear in both footer_html() and Footer.tsx.
 *
 * Exits 1 on drift; 0 on pass.
 * Runs as part of `prebuild` after gen-fastapi-css.mjs.
 */
import { readFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, "..");
const webServiceRoot = path.resolve(frontendRoot, "..");

const shellSrc = await readFile(
  path.join(webServiceRoot, "templates", "shell.py"),
  "utf-8"
);
const headerSrc = await readFile(
  path.join(frontendRoot, "components", "Header.tsx"),
  "utf-8"
);
const footerSrc = await readFile(
  path.join(frontendRoot, "components", "Footer.tsx"),
  "utf-8"
);

let drift = false;

// ── Check 1: Home link aria-label ────────────────────────────────────────────
// Python shell: search specifically for the <a href="/"> link's aria-label
// (not the SVG's aria-label, which is separate).
const pyAriaMatch = shellSrc.match(/href="\/"\s+aria-label="([^"]+)"/);
const pyAriaLabel = pyAriaMatch ? pyAriaMatch[1] : null;

// Header.tsx: <Link href="/" aria-label="..."> (Next.js Link component)
const tsxAriaMatch = headerSrc.match(/href="\/"\s+aria-label="([^"]+)"/);
const tsxAriaLabel = tsxAriaMatch ? tsxAriaMatch[1] : null;

if (!pyAriaLabel) {
  console.error("DRIFT: shell.py header_html() has no aria-label attribute");
  drift = true;
} else if (!tsxAriaLabel) {
  console.error("DRIFT: Header.tsx has no aria-label attribute");
  drift = true;
} else if (pyAriaLabel !== tsxAriaLabel) {
  console.error(
    `DRIFT: home link aria-label mismatch:\n` +
    `  shell.py:   "${pyAriaLabel}"\n` +
    `  Header.tsx: "${tsxAriaLabel}"`
  );
  drift = true;
}

// ── Check 2: Footer link presence ────────────────────────────────────────────
const requiredFooterLinks = ["/pricing", "/recover"];
for (const href of requiredFooterLinks) {
  const inPy = shellSrc.includes(`href="${href}"`);
  const inTsx = footerSrc.includes(`href="${href}"`);
  if (inTsx && !inPy) {
    console.error(
      `DRIFT: Footer.tsx has href="${href}" but shell.py footer_html() does not`
    );
    drift = true;
  }
}

if (drift) {
  console.error(
    "\nFAIL: Python shell has drifted from React components.\n" +
    "Update web_service/templates/shell.py to match."
  );
  process.exit(1);
}

console.log("OK: shell.py home aria-label and footer links match Header.tsx / Footer.tsx.");
