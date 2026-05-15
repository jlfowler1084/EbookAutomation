/**
 * EB-239 visual review: render icon.svg at 16, 32, 64px using sharp.
 * Outputs PNGs to the same directory for PR evidence.
 * Run from: web_service/frontend/  (requires node_modules with sharp)
 *   node ../../docs/visual-review/EB-239/render-preview.mjs
 */
import sharp from 'sharp';
import { readFileSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, '..', '..', '..', 'web_service', 'frontend');
const SVG_PATH = path.join(FRONTEND_ROOT, 'app', 'icon.svg');
const OUT_DIR = __dirname;

const svgBuffer = readFileSync(SVG_PATH);
console.log(`Source: ${SVG_PATH} (${svgBuffer.length} bytes)`);

for (const size of [16, 32, 64]) {
  const outPath = path.join(OUT_DIR, `icon-${size}px.png`);
  await sharp(svgBuffer).resize(size, size).png().toFile(outPath);
  console.log(`Written: ${outPath}`);
}
console.log('Done.');
