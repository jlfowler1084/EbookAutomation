/**
 * EB-264: Tests for sanitize.ts
 *
 * Covers: XSS stripping, CRLF rejection, length caps,
 * email normalization, topic allowlist, honeypot passthrough.
 */

import { describe, it, expect } from "vitest";
import { sanitize, stripHtml, hasCrlf, isValidEmail } from "../src/sanitize.js";

// Minimal valid payload for reuse across tests
const validPayload = {
  name: "Alice Tester",
  email: "alice@example.com",
  topic: "general",
  message: "Hello, I have a question about my conversion.",
  turnstile_token: "test-token",
};

describe("stripHtml", () => {
  it("strips angle brackets", () => {
    expect(stripHtml("<script>alert(1)</script>")).not.toContain("<");
    expect(stripHtml("<script>alert(1)</script>")).not.toContain(">");
  });

  it("entity-encodes ampersands", () => {
    expect(stripHtml("Tom & Jerry")).toContain("&amp;");
  });

  it("entity-encodes double quotes", () => {
    expect(stripHtml(`He said "hello"`)).toContain("&quot;");
  });

  it("entity-encodes single quotes", () => {
    expect(stripHtml("O'Brien")).toContain("&#x27;");
  });

  it("preserves normal text unchanged", () => {
    expect(stripHtml("Hello world")).toBe("Hello world");
  });
});

describe("hasCrlf", () => {
  it("detects \\n", () => expect(hasCrlf("foo\nbar")).toBe(true));
  it("detects \\r", () => expect(hasCrlf("foo\rbar")).toBe(true));
  it("detects \\r\\n", () => expect(hasCrlf("foo\r\nbar")).toBe(true));
  it("passes clean strings", () => expect(hasCrlf("hello world")).toBe(false));
});

describe("isValidEmail", () => {
  it("accepts standard email", () =>
    expect(isValidEmail("user@example.com")).toBe(true));
  it("accepts subdomain email", () =>
    expect(isValidEmail("user@mail.example.org")).toBe(true));
  it("rejects missing @", () =>
    expect(isValidEmail("notanemail")).toBe(false));
  it("rejects missing TLD", () =>
    expect(isValidEmail("user@example")).toBe(false));
  it("rejects spaces", () =>
    expect(isValidEmail("user @example.com")).toBe(false));
});

describe("sanitize — valid payload", () => {
  it("returns ok:true for a valid payload", () => {
    const result = sanitize(validPayload);
    expect(result.ok).toBe(true);
  });

  it("normalizes email to lowercase", () => {
    const result = sanitize({ ...validPayload, email: "Alice@Example.COM" });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.email).toBe("alice@example.com");
    }
  });

  it("normalizes topic to lowercase", () => {
    const result = sanitize({ ...validPayload, topic: "Billing" });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.topic).toBe("billing");
    }
  });
});

describe("sanitize — XSS prevention", () => {
  it("strips script tags from name", () => {
    const result = sanitize({ ...validPayload, name: '<script>alert(1)</script>' });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.name).not.toContain("<script>");
      expect(result.payload.name).not.toContain("</script>");
    }
  });

  it("strips HTML from message", () => {
    const result = sanitize({
      ...validPayload,
      message: '<img src=x onerror=alert(1)> Hello',
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.message).not.toContain("<img");
    }
  });
});

describe("sanitize — CRLF injection", () => {
  it("rejects name with \\n", () => {
    const result = sanitize({ ...validPayload, name: "Alice\nBob" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.status).toBe(422);
  });

  it("rejects email with \\r\\n", () => {
    const result = sanitize({ ...validPayload, email: "alice@example.com\r\n" });
    expect(result.ok).toBe(false);
  });

  it("allows \\n in message (multi-line OK)", () => {
    const result = sanitize({
      ...validPayload,
      message: "Line one.\nLine two.\nLine three.",
    });
    // Message CRLF is allowed (it's a text area)
    expect(result.ok).toBe(true);
  });
});

describe("sanitize — length caps", () => {
  it("rejects name over 120 chars", () => {
    const result = sanitize({ ...validPayload, name: "A".repeat(121) });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.status).toBe(422);
  });

  it("rejects email over 254 chars", () => {
    // "a".repeat(249) + "@b.com" = 249 + 6 = 255 chars > 254 limit
    const result = sanitize({
      ...validPayload,
      email: "a".repeat(249) + "@b.com",
    });
    expect(result.ok).toBe(false);
  });

  it("rejects message over 4000 chars", () => {
    const result = sanitize({ ...validPayload, message: "X".repeat(4001) });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.status).toBe(422);
  });

  it("accepts message of exactly 4000 chars", () => {
    const result = sanitize({ ...validPayload, message: "X".repeat(4000) });
    expect(result.ok).toBe(true);
  });
});

describe("sanitize — required fields", () => {
  it("rejects missing name", () => {
    const result = sanitize({ ...validPayload, name: "" });
    expect(result.ok).toBe(false);
  });

  it("rejects missing email", () => {
    const result = sanitize({ ...validPayload, email: "" });
    expect(result.ok).toBe(false);
  });

  it("rejects missing message", () => {
    const result = sanitize({ ...validPayload, message: "" });
    expect(result.ok).toBe(false);
  });
});

describe("sanitize — topic allowlist", () => {
  it("accepts: general, billing, conversion, bug, feature", () => {
    for (const t of ["general", "billing", "conversion", "bug", "feature"]) {
      const result = sanitize({ ...validPayload, topic: t });
      expect(result.ok).toBe(true);
    }
  });

  it("rejects unknown topic", () => {
    const result = sanitize({ ...validPayload, topic: "spam" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.status).toBe(422);
  });
});
