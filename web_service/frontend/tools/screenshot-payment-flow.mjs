#!/usr/bin/env node
/**
 * screenshot-payment-flow.mjs — EB-248 responsive smoke-test screenshots.
 *
 * Captures all 7 payment-flow states at 375px (mobile) and 1280px (desktop),
 * producing 14 PNGs in .screenshots/eb-248/. Used as PR evidence for R5.
 *
 * Prerequisites:
 *   - Local uvicorn server running: uvicorn web_service.main:app --port 8001
 *   - Or pass BASE_URL env var to point at a deployed instance
 *
 * Usage:
 *   node web_service/frontend/tools/screenshot-payment-flow.mjs
 *   BASE_URL=https://leafbind.io node screenshot-payment-flow.mjs
 */
import { chromium } from "playwright";
import { mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");

const BASE_URL = process.env.BASE_URL || "http://localhost:8001";
const OUT_DIR = path.join(repoRoot, ".screenshots", "eb-248");

// All 7 payment-flow states with descriptive labels and fixture URLs.
// Notes on each state:
//  - success: requires a real cs_ session with minted tokens in the DB, or
//    a special seed route if available. Use a known test session_id.
//  - expired: set session_id to a cs_ ID with past expires_at in the DB
//  - pending: session_id maps to a Stripe session with payment_status != "paid"
//  - retry: trigger circuit breaker open via the test harness, or use
//    ?_test_circuit_open=1 if the server supports a debug query param
//  - not_found: cs_ prefix but no matching Stripe session
//  - invalid: no cs_ prefix → 422
//  - cancel: /payment/cancel is always available

const STATES = [
  {
    name: "success",
    url: `${BASE_URL}/payment/success?session_id=cs_test_screenshot_seed`,
    note: "Seed a session in the DB before running",
  },
  {
    name: "expired",
    url: `${BASE_URL}/payment/success?session_id=cs_test_screenshot_expired`,
    note: "Seed an expired session in the DB before running",
  },
  {
    name: "pending",
    url: `${BASE_URL}/payment/success?session_id=cs_test_screenshot_pending`,
    note: "Stripe session with payment_status=unpaid",
  },
  {
    name: "retry",
    url: `${BASE_URL}/payment/success?session_id=cs_test_screenshot_retry`,
    note: "Trigger circuit breaker before visiting",
  },
  {
    name: "not-found",
    url: `${BASE_URL}/payment/success?session_id=cs_test_screenshot_notfound_xxxxxxxxxxx`,
    note: "Stripe InvalidRequestError — no matching session",
  },
  {
    name: "invalid",
    url: `${BASE_URL}/payment/success?session_id=bad_no_cs_prefix`,
    note: "Always available — fails prefix check",
  },
  {
    name: "cancel",
    url: `${BASE_URL}/payment/cancel`,
    note: "Static cancel page — always available",
  },
];

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "desktop", width: 1280, height: 800 },
];

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  let captured = 0;
  let skipped = 0;

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
    });
    const page = await ctx.newPage();

    for (const state of STATES) {
      const filename = `${state.name}-${vp.name}.png`;
      const outPath = path.join(OUT_DIR, filename);

      try {
        const response = await page.goto(state.url, { timeout: 8000 });
        const status = response?.status() ?? 0;

        // Allow 200, 404, 422, 503 — all are intentional states
        if (status === 0) {
          console.warn(`SKIP ${filename}: no response (server down?)`);
          skipped++;
          continue;
        }

        await page.screenshot({ path: outPath, fullPage: true });
        console.log(`  OK ${filename} (HTTP ${status})`);
        captured++;
      } catch (err) {
        console.warn(`SKIP ${filename}: ${err.message}`);
        skipped++;
      }
    }

    await ctx.close();
  }

  await browser.close();
  console.log(`\nDone: ${captured} captured, ${skipped} skipped → ${OUT_DIR}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
