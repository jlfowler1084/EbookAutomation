/**
 * EB-264: Input sanitization for the contact form Worker.
 *
 * Rules:
 * - Strip HTML tags (entity-encode < > &)
 * - Reject CRLF injection (\r\n, \n, \r) in name and subject fields
 * - Length caps: name ≤ 120, email ≤ 254, topic ≤ 40, message ≤ 4000
 * - Email normalization: .toLowerCase() before rate-limit keying
 *   (ensures User@Example.com and user@example.com share the same bucket)
 */

import type { ContactPayload, SanitizedPayload } from "./types.js";
import { TOPIC_ALLOWLIST } from "./types.js";

const NAME_MAX = 120;
const EMAIL_MAX = 254;
const TOPIC_MAX = 40;
const MESSAGE_MAX = 4000;

/** Strip HTML tags and entity-encode < > & */
export function stripHtml(input: string): string {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

/** Return true if the string contains CRLF sequences */
export function hasCrlf(input: string): boolean {
  return /[\r\n]/.test(input);
}

/** Basic email format validation (RFC 5321 simplified) */
export function isValidEmail(email: string): boolean {
  // Must have exactly one @, local part ≥ 1 char, domain has a dot
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export type SanitizeResult =
  | { ok: true; payload: SanitizedPayload }
  | { ok: false; error: string; status: number };

export function sanitize(raw: Partial<ContactPayload>): SanitizeResult {
  const { name, email, topic, message } = raw;

  // --- Presence checks ---
  if (!name || typeof name !== "string" || name.trim().length === 0) {
    return { ok: false, error: "Name is required.", status: 422 };
  }
  if (!email || typeof email !== "string" || email.trim().length === 0) {
    return { ok: false, error: "Email is required.", status: 422 };
  }
  if (!topic || typeof topic !== "string" || topic.trim().length === 0) {
    return { ok: false, error: "Topic is required.", status: 422 };
  }
  if (!message || typeof message !== "string" || message.trim().length === 0) {
    return { ok: false, error: "Message is required.", status: 422 };
  }

  // --- Length caps ---
  if (name.length > NAME_MAX) {
    return { ok: false, error: "Name is too long.", status: 422 };
  }
  if (email.length > EMAIL_MAX) {
    return { ok: false, error: "Email is too long.", status: 422 };
  }
  if (topic.length > TOPIC_MAX) {
    return { ok: false, error: "Topic is too long.", status: 422 };
  }
  if (message.length > MESSAGE_MAX) {
    return { ok: false, error: "Message is too long.", status: 422 };
  }

  // --- CRLF injection: only check single-line fields ---
  if (hasCrlf(name)) {
    return { ok: false, error: "Name contains invalid characters.", status: 422 };
  }
  if (hasCrlf(email)) {
    return { ok: false, error: "Email contains invalid characters.", status: 422 };
  }
  if (hasCrlf(topic)) {
    return { ok: false, error: "Topic contains invalid characters.", status: 422 };
  }

  // --- Email format ---
  const normalizedEmail = email.trim().toLowerCase();
  if (!isValidEmail(normalizedEmail)) {
    return { ok: false, error: "Email address is invalid.", status: 422 };
  }

  // --- Topic allowlist ---
  if (!TOPIC_ALLOWLIST.includes(topic.trim().toLowerCase() as typeof TOPIC_ALLOWLIST[number])) {
    return { ok: false, error: "Topic is not recognized.", status: 422 };
  }

  return {
    ok: true,
    payload: {
      name: stripHtml(name.trim()),
      email: normalizedEmail,
      topic: topic.trim().toLowerCase(),
      message: stripHtml(message.trim()),
    },
  };
}
