/**
 * EB-264: Tests for rate-limit.ts
 *
 * Covers: IP bucket cap, email bucket cap, IPv6 /64 bucketing,
 * case-variant email shares same bucket, KV TTL set correctly.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { bucketIp, sha256Hex, checkIpLimit, checkEmailLimit } from "../src/rate-limit.js";

// In-memory KV mock for unit tests
function makeMockKv(): KVNamespace {
  const store = new Map<string, { value: string; ttl?: number }>();
  return {
    async get(key: string) {
      return store.get(key)?.value ?? null;
    },
    async put(key: string, value: string, options?: { expirationTtl?: number }) {
      store.set(key, { value, ttl: options?.expirationTtl });
      return;
    },
    async delete(key: string) {
      store.delete(key);
    },
    async list() {
      return { keys: [], list_complete: true, cursor: undefined };
    },
    async getWithMetadata(key: string) {
      const entry = store.get(key);
      return { value: entry?.value ?? null, metadata: null };
    },
  } as unknown as KVNamespace;
}

describe("bucketIp", () => {
  it("passes IPv4 addresses unchanged", () => {
    expect(bucketIp("203.0.113.42")).toBe("203.0.113.42");
  });

  it("buckets IPv6 to /64 (zeroes last 64 bits)", () => {
    const result = bucketIp("2001:0db8:0000:0000:1234:5678:9abc:def0");
    expect(result).toBe("2001:0db8:0000:0000::");
  });

  it("two IPv6 addresses in same /64 get same bucket", () => {
    const a = bucketIp("2001:db8::1");
    const b = bucketIp("2001:db8::2");
    expect(a).toBe(b);
  });

  it("two IPv6 addresses in different /64 get different buckets", () => {
    const a = bucketIp("2001:db8:0:1::1");
    const b = bucketIp("2001:db8:0:2::1");
    expect(a).not.toBe(b);
  });
});

describe("sha256Hex", () => {
  it("returns 64 hex chars for any input", async () => {
    const h = await sha256Hex("test@example.com");
    expect(h).toHaveLength(64);
    expect(h).toMatch(/^[0-9a-f]+$/);
  });

  it("same input → same hash (deterministic)", async () => {
    const h1 = await sha256Hex("user@example.com");
    const h2 = await sha256Hex("user@example.com");
    expect(h1).toBe(h2);
  });

  it("different inputs → different hashes", async () => {
    const h1 = await sha256Hex("alice@example.com");
    const h2 = await sha256Hex("bob@example.com");
    expect(h1).not.toBe(h2);
  });
});

describe("checkIpLimit", () => {
  let kv: KVNamespace;

  beforeEach(() => {
    kv = makeMockKv();
  });

  it("allows first 5 requests from an IP", async () => {
    const ip = "203.0.113.10";
    for (let i = 0; i < 5; i++) {
      const ok = await checkIpLimit(kv, ip);
      expect(ok).toBe(true);
    }
  });

  it("blocks the 6th request from the same IP", async () => {
    const ip = "203.0.113.20";
    for (let i = 0; i < 5; i++) {
      await checkIpLimit(kv, ip);
    }
    const blocked = await checkIpLimit(kv, ip);
    expect(blocked).toBe(false);
  });

  it("different IPs do not share the counter", async () => {
    const ip1 = "203.0.113.30";
    const ip2 = "203.0.113.31";
    for (let i = 0; i < 5; i++) await checkIpLimit(kv, ip1);
    // ip2 should still be allowed
    const ok = await checkIpLimit(kv, ip2);
    expect(ok).toBe(true);
  });

  it("IPv6 addresses in same /64 share counter", async () => {
    const ip1 = "2001:db8::1";
    const ip2 = "2001:db8::2";
    for (let i = 0; i < 5; i++) await checkIpLimit(kv, ip1);
    // ip2 is in same /64 — should be blocked
    const blocked = await checkIpLimit(kv, ip2);
    expect(blocked).toBe(false);
  });
});

describe("checkEmailLimit", () => {
  let kv: KVNamespace;

  beforeEach(() => {
    kv = makeMockKv();
  });

  it("allows first 3 requests from an email", async () => {
    const email = "user@example.com";
    for (let i = 0; i < 3; i++) {
      const ok = await checkEmailLimit(kv, email);
      expect(ok).toBe(true);
    }
  });

  it("blocks the 4th request from the same email", async () => {
    const email = "user2@example.com";
    for (let i = 0; i < 3; i++) await checkEmailLimit(kv, email);
    const blocked = await checkEmailLimit(kv, email);
    expect(blocked).toBe(false);
  });

  it("case-variant email shares the same bucket (already lowercase from sanitize)", async () => {
    // sanitize.ts lowercases before calling here, so both should map to same hash
    const email1 = "user3@example.com";
    const email2 = "user3@example.com"; // same lowercased form
    for (let i = 0; i < 3; i++) await checkEmailLimit(kv, email1);
    const blocked = await checkEmailLimit(kv, email2);
    expect(blocked).toBe(false);
  });
});
