/**
 * EB-304: E2E Playwright tests for the FormatSelector upsell.
 *
 * Verifies the freemium UX on the home page upload widget:
 * - All three output formats are visible regardless of tier.
 * - KFX is labelled as Premium when no token is present.
 * - Selecting KFX as a free user surfaces an inline upsell with a CTA to
 *   /pricing#standard, and the dropzone reflects the gated state.
 * - Selecting a free format (EPUB/MOBI) clears the upsell and unblocks
 *   the dropzone.
 *
 * Tests run against the Next.js dev server (npm run dev).
 */

import { test, expect } from "@playwright/test";

test.describe("Home page — output format upsell (free tier)", () => {
  test("dropdown exposes all three formats with KFX marked Premium", async ({ page }) => {
    await page.goto("/");

    const select = page.getByLabel("Output format");
    await expect(select).toBeVisible();

    const optionValues = await select.locator("option").evaluateAll((opts) =>
      opts.map((o) => ({
        value: (o as HTMLOptionElement).value,
        text: (o as HTMLOptionElement).textContent?.trim() ?? "",
      })),
    );

    expect(optionValues.map((o) => o.value)).toEqual(["epub", "mobi", "kfx"]);
    expect(optionValues.find((o) => o.value === "kfx")?.text).toMatch(/Premium/);
    expect(optionValues.find((o) => o.value === "epub")?.text).not.toMatch(/Premium/);
  });

  test("selecting KFX surfaces upsell with link to /pricing#standard", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByTestId("format-upsell")).toHaveCount(0);

    await page.getByLabel("Output format").selectOption("kfx");

    const upsell = page.getByTestId("format-upsell");
    await expect(upsell).toBeVisible();
    await expect(upsell).toContainText("KFX");
    await expect(upsell.getByRole("link", { name: /buy credits/i })).toHaveAttribute(
      "href",
      "/pricing#standard",
    );
  });

  test("selecting KFX disables the dropzone and shows gated message", async ({ page }) => {
    await page.goto("/");

    await page.getByLabel("Output format").selectOption("kfx");

    const dropzone = page.getByRole("button", { name: /upload a pdf or ebook/i });
    await expect(dropzone).toHaveAttribute("aria-disabled", "true");
    await expect(dropzone).toContainText(/requires credits/i);
  });

  test("switching back to EPUB clears upsell and re-enables dropzone", async ({ page }) => {
    await page.goto("/");

    await page.getByLabel("Output format").selectOption("kfx");
    await expect(page.getByTestId("format-upsell")).toBeVisible();

    await page.getByLabel("Output format").selectOption("epub");
    await expect(page.getByTestId("format-upsell")).toHaveCount(0);

    const dropzone = page.getByRole("button", { name: /upload a pdf or ebook/i });
    await expect(dropzone).not.toHaveAttribute("aria-disabled", "true");
  });
});
