/**
 * EB-324 Unit 6: E2E tests for the result-page action cluster.
 *
 * The /status/[id] page polls GET {API}/status/{id}. These tests intercept
 * that request with fixtures for each state (done EPUB, with children,
 * expired source) and drive the action cluster: Download, Send-to-Kindle,
 * and per-format Re-convert rows.
 *
 * Screenshots are captured to test-results/ for visual review.
 */

import { expect, test } from "@playwright/test";

type StatusFixture = Record<string, unknown>;

function doneEpub(overrides: Partial<StatusFixture> = {}): StatusFixture {
  const future = Math.floor(Date.now() / 1000) + 50 * 60; // ~50 min out
  return {
    job_id: "test-job-123",
    status: "done",
    expires_at: future,
    source_present: true,
    output_present: true,
    kindle_delivery_status: null,
    resend_message_id: null,
    children: [],
    download_url: "/download/test-job-123",
    output_size: 1234567,
    ...overrides,
  };
}

// Scope the mock to the BACKEND API host (NEXT_PUBLIC_API_URL default
// localhost:8001) — NOT a bare "**/status/**", which would also intercept
// the Next.js page navigation at /status/[id] and serve raw JSON instead of
// the rendered page.
const API_HOST = "http://localhost:8001";

async function mockStatus(page: import("@playwright/test").Page, fixture: StatusFixture) {
  await page.route(`${API_HOST}/status/**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture),
    });
  });
}

test.describe("Result-page action cluster", () => {
  test("done EPUB job renders Download + Send-to-Kindle + convert rows", async ({ page }) => {
    await mockStatus(page, doneEpub());
    await page.goto("/status/test-job-123");

    // EPUB parent row: Download.
    await expect(page.getByRole("link", { name: /download epub/i })).toBeVisible();

    // Send-to-Kindle form (EPUB only).
    await expect(page.getByLabel(/your kindle email address/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /send to kindle/i })).toBeVisible();

    // MOBI (free) + KFX (premium) re-convert rows.
    await expect(page.getByRole("button", { name: /convert to mobi/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /convert to kfx — paste token/i })).toBeVisible();

    // Coarse TTL countdown.
    await expect(page.getByText(/these files are available for/i)).toBeVisible();

    await page.screenshot({
      path: "test-results/action-cluster-done-epub.png",
      fullPage: true,
    });
  });

  test("Send-to-Kindle happy path shows approved-sender success copy", async ({ page }) => {
    await mockStatus(page, doneEpub());
    await page.route(`${API_HOST}/send-to-kindle/**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "sent" }),
      });
    });
    await page.goto("/status/test-job-123");

    await page.getByLabel(/your kindle email address/i).fill("reader@kindle.com");
    await page.getByRole("button", { name: /^send to kindle$/i }).click();

    await expect(page.getByText(/sent to/i)).toBeVisible();
    await expect(page.getByText(/reader@kindle\.com/i)).toBeVisible();
    await expect(page.getByText(/approved personal document email list/i)).toBeVisible();

    await page.screenshot({
      path: "test-results/action-cluster-send-success.png",
      fullPage: true,
    });
  });

  test("invalid Kindle domain shows inline failure-generic error", async ({ page }) => {
    await mockStatus(page, doneEpub());
    await page.route(`${API_HOST}/send-to-kindle/**`, async (route) => {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: { error: "Recipient domain must be kindle.com or free.kindle.com", code: "INVALID_RECIPIENT_DOMAIN" },
        }),
      });
    });
    await page.goto("/status/test-job-123");

    await page.getByLabel(/your kindle email address/i).fill("reader@example.com");
    await page.getByRole("button", { name: /^send to kindle$/i }).click();

    await expect(page.getByText(/kindle\.com or free\.kindle\.com/i)).toBeVisible();
    // failure-generic: no troubleshooting link.
    await expect(page.getByRole("link", { name: /troubleshooting/i })).toHaveCount(0);
  });

  test("done MOBI child renders a Download row instead of a Convert button", async ({ page }) => {
    const future = Math.floor(Date.now() / 1000) + 50 * 60;
    await mockStatus(
      page,
      doneEpub({
        children: [
          {
            job_id: "child-mobi-1",
            format: "mobi",
            status: "done",
            expires_at: future,
            source_present: true,
            output_present: true,
            kindle_delivery_status: null,
            resend_message_id: null,
            download_url: "/download/child-mobi-1",
          },
        ],
      })
    );
    await page.goto("/status/test-job-123");

    // MOBI row now shows Download (the child), not a Convert button.
    await expect(page.getByRole("link", { name: /download mobi/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /convert to mobi/i })).toHaveCount(0);
    // KFX row still offers Convert.
    await expect(page.getByRole("button", { name: /convert to kfx/i })).toBeVisible();
  });

  test("expired source disables re-convert with session-expired copy", async ({ page }) => {
    await mockStatus(page, doneEpub({ source_present: false }));
    await page.goto("/status/test-job-123");

    const mobiBtn = page.getByRole("button", { name: /convert to mobi — session expired/i });
    await expect(mobiBtn).toBeVisible();
    await expect(mobiBtn).toHaveAttribute("aria-disabled", "true");

    await page.screenshot({
      path: "test-results/action-cluster-expired.png",
      fullPage: true,
    });
  });

  test("bounced delivery status surfaces approved-sender failure-known copy", async ({ page }) => {
    await mockStatus(page, doneEpub({ kindle_delivery_status: "bounced" }));
    await page.goto("/status/test-job-123");

    await expect(page.getByText(/amazon didn'?t accept this delivery/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /troubleshooting/i })).toBeVisible();
  });
});
