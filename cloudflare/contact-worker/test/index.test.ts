/**
 * EB-264: Integration tests for the contact Worker (index.ts).
 *
 * Tests the full request lifecycle using a stub environment.
 * Runs in Node.js (not Workers runtime). Uses the native fetch/Request/Response
 * available in Node 18+ (and Node 24 which is the project standard).
 *
 * Covers: CORS preflight, honeypot bypass, valid submission flow,
 * Turnstile failure, sanitization errors.
 */

import { describe, it, expect, vi, afterEach } from "vitest";

afterEach(() => {
  vi.restoreAllMocks();
});

// Minimal in-memory KV mock
function makeMockKv() {
  const store = new Map<string, string>();
  return {
    async get(key: string): Promise<string | null> {
      return store.get(key) ?? null;
    },
    async put(key: string, value: string, _options?: { expirationTtl?: number }): Promise<void> {
      store.set(key, value);
    },
    async delete(key: string): Promise<void> {
      store.delete(key);
    },
    async list() {
      return { keys: [], list_complete: true, cursor: undefined };
    },
    async getWithMetadata(key: string) {
      return { value: store.get(key) ?? null, metadata: null };
    },
  };
}

// Minimal Env stub matching the Env interface
function makeEnv() {
  return {
    CONTACT_KV: makeMockKv(),
    TURNSTILE_SECRET_KEY: "test-secret",
    RESEND_API_KEY: "re_test",
    SUPPORT_INBOX_ADDRESS: "support@leafbind.io",
  };
}

// Valid POST body
const validBody = {
  name: "Test User",
  email: "test@example.com",
  topic: "general",
  message: "This is a test message for the contact form.",
  turnstile_token: "valid-token",
};

function makeRequest(
  body: object,
  origin = "https://leafbind.io",
  method = "POST"
): Request {
  return new Request("https://forms.leafbind.io/contact", {
    method,
    headers: {
      "Content-Type": "application/json",
      Origin: origin,
      "CF-Connecting-IP": "203.0.113.1",
    },
    body: method === "POST" ? JSON.stringify(body) : undefined,
  });
}

async function getWorker() {
  return (await import("../src/index.js")).default;
}

describe("OPTIONS preflight", () => {
  it("returns 204 with CORS headers for allowed origin", async () => {
    const worker = await getWorker();
    const req = new Request("https://forms.leafbind.io/contact", {
      method: "OPTIONS",
      headers: { Origin: "https://leafbind.io" },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(204);
    expect(resp.headers.get("Access-Control-Allow-Origin")).toBe("https://leafbind.io");
  });

  it("returns 403 for disallowed origin", async () => {
    const worker = await getWorker();
    const req = new Request("https://forms.leafbind.io/contact", {
      method: "OPTIONS",
      headers: { Origin: "https://evil.com" },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(403);
  });
});

describe("Method gating", () => {
  it("returns 405 for GET requests", async () => {
    const worker = await getWorker();
    const req = new Request("https://forms.leafbind.io/contact", {
      method: "GET",
      headers: { Origin: "https://leafbind.io" },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(405);
  });
});

describe("Honeypot", () => {
  it("returns 200 ok:true for honeypot-filled requests (oracle prevention)", async () => {
    const worker = await getWorker();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const req = makeRequest({ ...validBody, honeypot: "bot-filled" });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(200);
    const json = await resp.json() as { ok: boolean };
    expect(json.ok).toBe(true);

    // fetch should NOT have been called (no Turnstile, no Resend)
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("Valid submission", () => {
  it("returns 200 ok:true for a valid payload with passing Turnstile", async () => {
    const worker = await getWorker();

    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("turnstile")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true }),
          text: () => Promise.resolve(""),
        });
      }
      // Resend calls
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ id: "mock-email-id" }),
        text: () => Promise.resolve(""),
      });
    }));

    const req = makeRequest(validBody);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(200);
    const json = await resp.json() as { ok: boolean };
    expect(json.ok).toBe(true);
  });
});

describe("Turnstile failure", () => {
  it("returns 400 when Turnstile token fails verification", async () => {
    const worker = await getWorker();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: false }),
      text: () => Promise.resolve(""),
    }));

    const req = makeRequest(validBody);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(400);
    const json = await resp.json() as { ok: boolean };
    expect(json.ok).toBe(false);
  });
});

describe("Sanitization errors surface as 422", () => {
  it("returns 422 for missing name", async () => {
    const worker = await getWorker();
    vi.stubGlobal("fetch", vi.fn());

    const req = makeRequest({ ...validBody, name: "" });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(422);
  });

  it("returns 422 for unknown topic", async () => {
    const worker = await getWorker();
    vi.stubGlobal("fetch", vi.fn());

    const req = makeRequest({ ...validBody, topic: "hacking" });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(422);
  });
});

describe("Missing Turnstile token", () => {
  it("returns 400 when turnstile_token is empty", async () => {
    const worker = await getWorker();
    vi.stubGlobal("fetch", vi.fn());

    const req = makeRequest({ ...validBody, turnstile_token: "" });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resp = await worker.fetch(req, makeEnv() as any);
    expect(resp.status).toBe(400);
  });
});
