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

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
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
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
