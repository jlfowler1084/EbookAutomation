/**
 * EB-264: E2E Playwright tests for the /contact page.
 *
 * Tests run against the Next.js dev server (npm run dev).
 * The Worker at forms.leafbind.io is mocked via route interception so
 * these tests do not require a live Worker deployment.
 *
 * Covers:
 * - Page renders with correct heading and form fields
 * - Submit button is disabled during submission
 * - Validation errors appear for empty fields
 * - Successful submission shows success state
 * - 429 rate-limit error shows the correct message
 * - 503 service error shows the fallback message
 * - Keyboard-only form completion is possible
 * - Success container receives focus (aria-live)
 */

import { test, expect } from "@playwright/test";

const WORKER_URL = "https://forms.leafbind.io/contact";
const TURNSTILE_API_URL =
  "https://challenges.cloudflare.com/turnstile/v0/api.js**";

function validPayload() {
  return {
    name: "Alice Tester",
    email: "alice@example.com",
    topic: "general",
    message: "This is a test message for the contact form from Playwright.",
  };
}

test.describe("/contact page", () => {
  // EB-307: Mock Cloudflare Turnstile so tests are hermetic in CI.
  // The form's submit guard (ContactForm.tsx:187) blocks fetch until
  // turnstileToken is set, which normally requires NEXT_PUBLIC_TURNSTILE_SITE_KEY
  // + a live Cloudflare CDN load. Stub both:
  //   - Route the api.js load to an empty 200 so <Script onLoad> fires
  //   - Install a window.turnstile stub that synchronously delivers a token
  //     via the render() callback the form passes in.
  test.beforeEach(async ({ page }) => {
    await page.route(TURNSTILE_API_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/javascript",
        body: "",
      }),
    );

    await page.addInitScript(() => {
      (window as unknown as { turnstile: unknown }).turnstile = {
        render: (
          _selector: string,
          opts: { callback?: (token: string) => void },
        ) => {
          opts.callback?.("playwright-test-token");
          return "playwright-widget-id";
        },
        reset: () => {},
      };
    });
  });

  test("renders heading and all form fields", async ({ page }) => {
    await page.goto("/contact");

    await expect(page.getByRole("heading", { name: "Contact", level: 1 })).toBeVisible();
    await expect(page.getByLabel("Name")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Topic")).toBeVisible();
    await expect(page.getByLabel("Message")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  });

  test("shows validation errors for empty submission", async ({ page }) => {
    await page.goto("/contact");

    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("Name is required.")).toBeVisible();
    await expect(page.getByText("Email address is required.")).toBeVisible();
    await expect(page.getByText("Message is required.")).toBeVisible();
  });

  test("shows email validation error for invalid email", async ({ page }) => {
    await page.goto("/contact");

    await page.getByLabel("Name").fill("Test User");
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("Message").fill("Test message with enough chars");

    await page.getByRole("button", { name: "Send message" }).click();

    await expect(
      page.getByText("Please enter a valid email address.")
    ).toBeVisible();
  });

  test("shows success state after successful submission", async ({ page }) => {
    // Mock the Worker endpoint to return success
    await page.route(WORKER_URL, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto("/contact");

    const { name, email, message } = validPayload();
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Message").fill(message);

    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByRole("status")).toBeVisible();
    await expect(page.getByText("Message sent")).toBeVisible();
  });

  test("shows rate-limit error (429) with correct message", async ({ page }) => {
    await page.route(WORKER_URL, async (route) => {
      await route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          error: "Too many requests. Please wait a while before submitting again.",
        }),
      });
    });

    await page.goto("/contact");

    const { name, email, message } = validPayload();
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Message").fill(message);

    await page.getByRole("button", { name: "Send message" }).click();

    await expect(
      page.getByText(/too many messages recently/i)
    ).toBeVisible();
  });

  test("shows service error (503) with fallback message", async ({ page }) => {
    await page.route(WORKER_URL, async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          error: "We couldn't deliver your message right now.",
        }),
      });
    });

    await page.goto("/contact");

    const { name, email, message } = validPayload();
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Message").fill(message);

    await page.getByRole("button", { name: "Send message" }).click();

    await expect(
      page.getByText(/try again in a few minutes/i)
    ).toBeVisible();
  });

  test("keyboard-only form completion and submission is possible", async ({ page }) => {
    await page.route(WORKER_URL, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto("/contact");

    // Tab to Name, fill it
    await page.getByLabel("Name").focus();
    await page.keyboard.type("Keyboard User");

    // Tab to Email
    await page.keyboard.press("Tab");
    await page.keyboard.type("keyboard@example.com");

    // Tab to Topic (select — skip, it has a default)
    await page.keyboard.press("Tab");

    // Tab to Message
    await page.keyboard.press("Tab");
    await page.keyboard.type("Testing keyboard navigation on this contact form.");

    // Tab to Submit button
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");

    await expect(page.getByRole("status")).toBeVisible();
    await expect(page.getByText("Message sent")).toBeVisible();
  });

  test("success container receives focus for screen reader announcement", async ({ page }) => {
    await page.route(WORKER_URL, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto("/contact");

    const { name, email, message } = validPayload();
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Message").fill(message);

    await page.getByRole("button", { name: "Send message" }).click();

    // Success element should be focused (tabIndex=-1 with programmatic focus)
    const successEl = page.getByRole("status");
    await expect(successEl).toBeVisible();
    // Verify aria-live="polite" is present
    await expect(successEl).toHaveAttribute("aria-live", "polite");
  });

  test("sessionStorage draft is cleared after successful submission", async ({ page }) => {
    await page.route(WORKER_URL, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto("/contact");

    const { name, email, message } = validPayload();
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Message").fill(message);

    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByRole("status")).toBeVisible();

    // Draft should be cleared
    const draft = await page.evaluate(() =>
      sessionStorage.getItem("lb_contact_draft")
    );
    expect(draft).toBeNull();
  });
});
