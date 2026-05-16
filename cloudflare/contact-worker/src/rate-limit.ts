/**
 * EB-264: KV-backed rate limiting for the contact form Worker.
 *
 * Design:
 * - Single KV namespace (CONTACT_KV) with key prefixes:
 *     rl:ip:<bucket>:<ipKey>   — per-IP window counter
 *     rl:email:<bucket>:<hash> — per-email window counter
 * - Fixed-window: floor(unix_seconds / 3600) — 1-hour buckets.
 *   Known limitation: at the hour boundary an attacker can get 2× cap in ~2s.
 *   Acceptable for v1 volume; upgrade to 2-bucket sliding window if abused.
 * - KV is eventually consistent (~60s globally). Different colos can briefly
 *   bypass the bucket cap by reading stale counters. Accepted for v1.
 * - IPv6 /64 bucketing: collapse last 64 bits to prevent trivial bypass
 *   by rotating addresses within the same /64.
 * - Email normalization: already done by sanitize.ts (lowercase); hash here.
 */

const IP_LIMIT = 5;    // per hour per IP (/64 for IPv6)
const EMAIL_LIMIT = 3; // per hour per normalized email address
const TTL_SECONDS = 3600; // 1 hour

/** Current 1-hour window bucket (fixed-window) */
function currentBucket(): number {
  return Math.floor(Date.now() / 1_000 / 3600);
}

/**
 * Bucket IPv6 addresses to /64 by zeroing the last 64 bits.
 * IPv4 addresses pass through unchanged.
 */
export function bucketIp(ip: string): string {
  if (!ip.includes(":")) {
    // IPv4 — use as-is
    return ip;
  }
  // IPv6 — expand and zero the last 64 bits
  // Simple approach: split on ":" and keep first 4 groups (64 bits)
  const parts = expandIpv6(ip).split(":");
  return parts.slice(0, 4).join(":") + "::";
}

/** Expand IPv6 shorthand to full 8-group form */
function expandIpv6(ip: string): string {
  // Handle :: shorthand
  if (ip.includes("::")) {
    const [left, right] = ip.split("::");
    const leftParts = left ? left.split(":") : [];
    const rightParts = right ? right.split(":") : [];
    const missing = 8 - leftParts.length - rightParts.length;
    const middle = Array(missing).fill("0000");
    return [...leftParts, ...middle, ...rightParts]
      .map((p) => p.padStart(4, "0"))
      .join(":");
  }
  return ip
    .split(":")
    .map((p) => p.padStart(4, "0"))
    .join(":");
}

/** SHA-256 hash of a string, hex-encoded (for email keying) */
export async function sha256Hex(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Check and increment the rate-limit counter for this IP.
 * Returns true if the request should be allowed, false if rate-limited.
 */
export async function checkIpLimit(
  kv: KVNamespace,
  ip: string
): Promise<boolean> {
  const bucket = currentBucket();
  const ipKey = bucketIp(ip);
  const kvKey = `rl:ip:${bucket}:${ipKey}`;

  const raw = await kv.get(kvKey);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= IP_LIMIT) {
    return false;
  }

  await kv.put(kvKey, String(count + 1), { expirationTtl: TTL_SECONDS });
  return true;
}

/**
 * Check and increment the rate-limit counter for this email.
 * Email must already be lowercased (done by sanitize.ts).
 */
export async function checkEmailLimit(
  kv: KVNamespace,
  email: string
): Promise<boolean> {
  const bucket = currentBucket();
  const emailHash = await sha256Hex(email);
  const kvKey = `rl:email:${bucket}:${emailHash}`;

  const raw = await kv.get(kvKey);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= EMAIL_LIMIT) {
    return false;
  }

  await kv.put(kvKey, String(count + 1), { expirationTtl: TTL_SECONDS });
  return true;
}
