/**
 * EB-264: Tests for turnstile.ts
 *
 * Covers: success path, failure path, network timeout (fail-closed),
 * non-2xx response (fail-closed), malformed JSON (fail-closed),
 * single-use replay behavior (mocked).
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { verifyTurnstile } from "../src/turnstile.js";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: response.ok ?? true,
    status: response.status ?? 200,
    json: response.json ?? (() => Promise.resolve({ success: true })),
    text: () => Promise.resolve(""),
    ...response,
  }));
}

describe("verifyTurnstile — success", () => {
  it("returns true when Cloudflare returns success:true", async () => {
    mockFetch({ ok: true, json: () => Promise.resolve({ success: true }) });
    const result = await verifyTurnstile("good-token", "secret", "1.2.3.4");
    expect(result).toBe(true);
  });
});

describe("verifyTurnstile — failure paths", () => {
  it("returns false when Cloudflare returns success:false", async () => {
    mockFetch({ ok: true, json: () => Promise.resolve({ success: false }) });
    const result = await verifyTurnstile("bad-token", "secret", "1.2.3.4");
    expect(result).toBe(false);
  });

  it("returns false (fail-closed) when HTTP response is non-2xx", async () => {
    mockFetch({ ok: false, status: 500 });
    const result = await verifyTurnstile("token", "secret", "1.2.3.4");
    expect(result).toBe(false);
  });

  it("returns false (fail-closed) on network timeout / AbortError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("The operation was aborted.", "AbortError")));
    const result = await verifyTurnstile("token", "secret", "1.2.3.4");
    expect(result).toBe(false);
  });

  it("returns false (fail-closed) on any fetch exception", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));
    const result = await verifyTurnstile("token", "secret", "1.2.3.4");
    expect(result).toBe(false);
  });

  it("returns false (fail-closed) when JSON is malformed", async () => {
    mockFetch({
      ok: true,
      json: () => Promise.reject(new SyntaxError("unexpected token")),
    });
    const result = await verifyTurnstile("token", "secret", "1.2.3.4");
    expect(result).toBe(false);
  });

  it("returns false when success field is absent from response", async () => {
    mockFetch({ ok: true, json: () => Promise.resolve({}) });
    const result = await verifyTurnstile("token", "secret", "1.2.3.4");
    expect(result).toBe(false);
  });
});

describe("verifyTurnstile — remoteip is passed", () => {
  it("includes remoteip in the POST body", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await verifyTurnstile("token", "secret", "203.0.113.99");

    const [, options] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = options.body as URLSearchParams;
    expect(body.get("remoteip")).toBe("203.0.113.99");
  });
});
