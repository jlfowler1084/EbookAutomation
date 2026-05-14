/**
 * Build favicon.ico (multi-resolution: 16x16, 32x32, 48x48) and
 * apple-icon.png (180x180) from app/icon.svg using sharp + png-to-ico.
 *
 * Idempotent: safe to run multiple times.
 * Wire into package.json as: "build:icons": "node tools/build-icons.mjs"
 *
 * Usage: node tools/build-icons.mjs
 */
import sharp from 'sharp';
import pngToIco from 'png-to-ico';
import { readFileSync, writeFileSync, statSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, '..');
const SVG_PATH = path.join(FRONTEND_ROOT, 'app', 'icon.svg');
const FAVICON_PATH = path.join(FRONTEND_ROOT, 'app', 'favicon.ico');
const APPLE_ICON_PATH = path.join(FRONTEND_ROOT, 'app', 'apple-icon.png');

// Brand cream background for apple-icon (iOS home screen renders on white by default)
const APPLE_BG = { r: 250, g: 248, b: 243, alpha: 1 };

async function rasterizeSvg(svgPath, size) {
  const svgBuffer = readFileSync(svgPath);
  return sharp(svgBuffer)
    .resize(size, size)
    .png()
    .toBuffer();
}

async function main() {
  const svgBuffer = readFileSync(SVG_PATH);
  console.log(`Source SVG: ${SVG_PATH} (${svgBuffer.length} bytes)`);

  // --- favicon.ico: 16x16, 32x32, 48x48 ---
  console.log('Generating favicon PNG layers: 16, 32, 48...');
  const [png16, png32, png48] = await Promise.all([
    rasterizeSvg(SVG_PATH, 16),
    rasterizeSvg(SVG_PATH, 32),
    rasterizeSvg(SVG_PATH, 48),
  ]);

  const icoBuffer = await pngToIco([png16, png32, png48]);
  writeFileSync(FAVICON_PATH, icoBuffer);
  const icoStat = statSync(FAVICON_PATH);
  console.log(`favicon.ico written: ${FAVICON_PATH} (${icoStat.size} bytes)`);

  // --- apple-icon.png: 180x180 with brand-cream background ---
  console.log('Generating apple-icon.png at 180x180 with cream background...');
  const leafPng180 = await rasterizeSvg(SVG_PATH, 180);

  // Composite leaf onto cream background
  await sharp({
    create: {
      width: 180,
      height: 180,
      channels: 4,
      background: APPLE_BG,
    },
  })
    .composite([{ input: leafPng180, blend: 'over' }])
    .png()
    .toFile(APPLE_ICON_PATH);

  const appleStat = statSync(APPLE_ICON_PATH);
  console.log(`apple-icon.png written: ${APPLE_ICON_PATH} (${appleStat.size} bytes)`);

  console.log('Done.');
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
