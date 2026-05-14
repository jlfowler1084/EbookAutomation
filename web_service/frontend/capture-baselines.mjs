/**
 * EB-233 Pre-redesign baseline capture script
 * Snapshots 9 routes at desktop (1440x900) and mobile (375x667) widths
 * against https://leafbind.io
 *
 * Usage: node capture-baselines.mjs
 */
import { chromium } from 'playwright';
import { mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_URL = 'https://leafbind.io';
const OUTPUT_DIR = path.join(__dirname, '.baselines', 'eb233-pre');

const ROUTES = [
  { slug: 'home', path: '/' },
  { slug: 'pricing', path: '/pricing' },
  { slug: 'quality', path: '/quality' },
  { slug: 'recover', path: '/recover' },
  { slug: 'status-test-id', path: '/status/test-id-12345' },
  { slug: 'convert-pdf-to-kfx', path: '/convert/pdf-to-kfx' },
  { slug: 'convert-academic-pdf-to-kindle', path: '/convert/academic-pdf-to-kindle' },
  { slug: 'convert-pdf-footnotes-kindle', path: '/convert/pdf-footnotes-kindle' },
  { slug: 'convert-multi-column-pdf-kindle', path: '/convert/multi-column-pdf-kindle' },
];

const VIEWPORTS = [
  { name: '1440x900', width: 1440, height: 900 },
  { name: '375x667', width: 375, height: 667 },
];

async function main() {
  if (!existsSync(OUTPUT_DIR)) {
    await mkdir(OUTPUT_DIR, { recursive: true });
  }

  const browser = await chromium.launch({ headless: true });
  const results = [];

  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();

    for (const route of ROUTES) {
      const url = `${BASE_URL}${route.path}`;
      const filename = `${route.slug}-${viewport.name}.png`;
      const outputPath = path.join(OUTPUT_DIR, filename);

      try {
        console.log(`Capturing ${filename} from ${url}...`);
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        // Wait a bit for any deferred rendering
        await page.waitForTimeout(1000);
        await page.screenshot({ path: outputPath, fullPage: false });
        const stat = await import('fs').then(fs => fs.statSync(outputPath));
        results.push({ file: filename, size: stat.size, status: 'ok' });
        console.log(`  -> saved ${filename} (${stat.size} bytes)`);
      } catch (err) {
        console.error(`  -> FAILED ${filename}: ${err.message}`);
        results.push({ file: filename, size: 0, status: 'error', error: err.message });
      }
    }

    await context.close();
  }

  await browser.close();

  // Print summary
  const ok = results.filter(r => r.status === 'ok').length;
  const failed = results.filter(r => r.status === 'error').length;
  console.log(`\nSummary: ${ok} captured, ${failed} failed`);
  if (failed > 0) {
    results.filter(r => r.status === 'error').forEach(r => {
      console.error(`  FAILED: ${r.file} — ${r.error}`);
    });
    process.exit(1);
  }

  // Write results JSON for manifest generation
  const resultsPath = path.join(OUTPUT_DIR, 'capture-results.json');
  import('fs').then(fs => {
    fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));
  });

  return results;
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
