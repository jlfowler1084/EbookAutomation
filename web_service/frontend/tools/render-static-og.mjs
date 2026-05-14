/**
 * Render the static OG/Twitter images from og-template.html via Playwright.
 * Outputs:
 *   app/opengraph-image.png  (1200x630)
 *   app/twitter-image.png    (1200x600, cropped from same render)
 *
 * Usage: node tools/render-static-og.mjs
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';
import { statSync } from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, '..');
const HTML_PATH = path.join(FRONTEND_ROOT, '.baselines', 'eb233-logo-preview', 'og-template.html');
const OG_OUTPUT = path.join(FRONTEND_ROOT, 'app', 'opengraph-image.png');
const TWITTER_OUTPUT = path.join(FRONTEND_ROOT, 'app', 'twitter-image.png');

const MIN_BYTES = 30_000;

async function main() {
  const browser = await chromium.launch({ headless: true });

  // Render OG image at 1200x630
  {
    const context = await browser.newContext({
      viewport: { width: 1200, height: 630 },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const fileUrl = 'file://' + HTML_PATH.replace(/\\/g, '/');
    console.log(`Loading ${fileUrl} for OG render (1200x630)...`);
    await page.goto(fileUrl, { waitUntil: 'networkidle' });
    await page.waitForTimeout(600);
    await page.screenshot({ path: OG_OUTPUT, clip: { x: 0, y: 0, width: 1200, height: 630 } });
    await context.close();
    const stat = statSync(OG_OUTPUT);
    console.log(`OG image saved: ${OG_OUTPUT} (${stat.size} bytes)`);
    if (stat.size < MIN_BYTES) {
      throw new Error(`OG image is too small (${stat.size} bytes < ${MIN_BYTES}) — render may have failed`);
    }
  }

  // Render Twitter card at 1200x600 (re-render with shorter viewport)
  {
    const context = await browser.newContext({
      viewport: { width: 1200, height: 600 },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const fileUrl = 'file://' + HTML_PATH.replace(/\\/g, '/');
    console.log(`Loading ${fileUrl} for Twitter render (1200x600)...`);
    await page.goto(fileUrl, { waitUntil: 'networkidle' });
    await page.waitForTimeout(600);
    await page.screenshot({ path: TWITTER_OUTPUT, clip: { x: 0, y: 0, width: 1200, height: 600 } });
    await context.close();
    const stat = statSync(TWITTER_OUTPUT);
    console.log(`Twitter image saved: ${TWITTER_OUTPUT} (${stat.size} bytes)`);
    if (stat.size < MIN_BYTES) {
      throw new Error(`Twitter image is too small (${stat.size} bytes < ${MIN_BYTES}) — render may have failed`);
    }
  }

  await browser.close();
  console.log('Done. Both images rendered successfully.');
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
