/**
 * EB-264: First Playwright config for the leafbind frontend.
 *
 * Runs E2E tests against the local Next.js dev server (npm run dev).
 * Tests live in web_service/frontend/tests/.
 *
 * Usage:
 *   npm run test:e2e          — run all E2E tests
 *   npm run test:e2e -- --ui  — open Playwright UI
 *
 * Test artifacts (test-results/, playwright-report/) are gitignored.
 */

import { defineConfig, devices } from "@playwright/test";

// EB-324 Unit 6: the dev port is configurable via LEAFBIND_TEST_PORT so the
// suite can dodge a port-3000 collision with a sibling project's dev server
// (e.g., CareerPilot also runs Next.js on :3000 locally). Defaults to 3000
// to match CI + existing local convention.
const PORT = process.env.LEAFBIND_TEST_PORT ?? "3000";
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "html",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Start the dev server automatically if not already running
  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // EB-307: Cloudflare-published always-passes test sitekey. ContactForm's
      // onTurnstileScriptLoad() early-returns when this is empty, so without it
      // the form never wires up — even with the window.turnstile stub from
      // contact-form.spec.ts beforeEach. Setting it here keeps tests hermetic
      // in CI and overrides any developer .env.local during local test runs.
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: "1x00000000000000000000AA",
    },
  },
});
