#!/usr/bin/env node
/**
 * CI internal-link checker for EB-295.
 *
 * Walks all *.tsx files under app/, extracts every <Link href="/..."> literal
 * (static string hrefs only — no template literals), and verifies each path
 * resolves to a page.tsx under app/.
 *
 * Exits 1 on any unresolved link, printing the offending file and href.
 * Run as part of `prebuild` so broken internal links fail the build.
 *
 * Rules:
 *   - Only checks <Link href="..."> (Next.js Link component), not <a href>
 *   - Only checks absolute paths starting with "/"
 *   - Strips query strings and fragments before checking
 *   - Skips dynamic segments ([param]) — those can't be statically verified
 *   - Route groups like (marketing) are transparent in Next.js routing
 */
import { readFile, readdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(__dirname, "..", "app");

// ── Collect page paths ────────────────────────────────────────────────────────

async function collectPagePaths(dir, pagePaths = new Set()) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await collectPagePaths(fullPath, pagePaths);
    } else if (
      entry.name === "page.tsx" ||
      entry.name === "page.jsx" ||
      entry.name === "page.ts" ||
      entry.name === "page.js"
    ) {
      const rel = path.relative(appDir, path.dirname(fullPath));
      const segments = rel
        .split(/[/\\]/)
        .filter((seg) => seg !== "" && !seg.startsWith("(")) // strip route groups
        .filter((seg) => !seg.startsWith("["));              // skip dynamic segments
      const urlPath = segments.length === 0 ? "/" : "/" + segments.join("/");
      pagePaths.add(urlPath);
    }
  }
  return pagePaths;
}

// ── Collect TSX files ─────────────────────────────────────────────────────────

async function collectTsxFiles(dir, files = []) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await collectTsxFiles(fullPath, files);
    } else if (entry.name.endsWith(".tsx") || entry.name.endsWith(".jsx")) {
      files.push(fullPath);
    }
  }
  return files;
}

// ── Extract <Link href="/..."> static hrefs ───────────────────────────────────

function extractLinkHrefs(source) {
  const hrefs = [];
  // Match: href="/..." or href='/...' (static strings, not template literals)
  const re = /\bLink\b[^>]*?\bhref=["'](\/.+?)["']/g;
  let m;
  while ((m = re.exec(source)) !== null) {
    let href = m[1];
    // Strip fragment and query string
    href = href.replace(/[?#].*$/, "");
    if (href.startsWith("/")) {
      hrefs.push(href);
    }
  }
  return hrefs;
}

// ── Main ──────────────────────────────────────────────────────────────────────

const pagePaths = await collectPagePaths(appDir);
const tsxFiles = await collectTsxFiles(appDir);

let failures = 0;

for (const file of tsxFiles) {
  const source = await readFile(file, "utf-8");
  const hrefs = extractLinkHrefs(source);
  for (const href of hrefs) {
    if (!pagePaths.has(href)) {
      const rel = path.relative(path.resolve(__dirname, ".."), file).replace(/\\/g, "/");
      console.error(`DEAD LINK [${rel}]: <Link href="${href}"> — no page.tsx found at app${href}`);
      failures++;
    }
  }
}

if (failures > 0) {
  console.error(`\nFAIL: ${failures} dead internal link(s) found. Add page.tsx for each target or remove the link.`);
  process.exit(1);
}

console.log(`OK: ${tsxFiles.length} files checked, all <Link href="/..."> hrefs resolve to a page.tsx.`);
