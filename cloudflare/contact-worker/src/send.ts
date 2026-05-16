/**
 * EB-264: Email sending via Resend REST API.
 *
 * Two emails per submission:
 * 1. Operator notification → SUPPORT_INBOX_ADDRESS (support@leafbind.io)
 * 2. Auto-acknowledgement → submitter's email
 *
 * Rules:
 * - Plain-text only (no HTML in either email body).
 * - Auto-ack throttle: keyed ack:<sha256(lowercase_email)> in CONTACT_KV.
 *   TTL = 24h. If the key exists, skip auto-ack (submitter already got one today).
 *   Auto-ack failure does NOT block operator notification.
 * - From: field uses support@leafbind.io.
 *   Resend signs DKIM with d=leafbind.io; MAIL FROM is via send.leafbind.io subdomain.
 *   The Worker does NOT manage SPF — that is DNS-level configuration.
 * - Never log the email address or API key.
 */

import { sha256Hex } from "./rate-limit.js";
import type { Env, SanitizedPayload } from "./types.js";

const RESEND_API_URL = "https://api.resend.com/emails";
const ACK_TTL_SECONDS = 86_400; // 24 hours

async function sendViaResend(
  apiKey: string,
  to: string,
  from: string,
  replyTo: string | undefined,
  subject: string,
  text: string
): Promise<void> {
  const body: Record<string, unknown> = { from, to, subject, text };
  if (replyTo) body.reply_to = replyTo;

  const resp = await fetch(RESEND_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    // Include status but NOT the API key or email in logs
    const detail = await resp.text().catch(() => "(unreadable)");
    throw new Error(`Resend API error ${resp.status}: ${detail.slice(0, 200)}`);
  }
}

/**
 * Send operator notification and (if not throttled) user auto-ack.
 * Returns true if operator notification succeeded; auto-ack result is advisory.
 */
export async function sendContactEmails(
  env: Env,
  payload: SanitizedPayload
): Promise<void> {
  const { name, email, topic, message } = payload;
  const supportAddress = env.SUPPORT_INBOX_ADDRESS;

  // 1. Operator notification (load-bearing — failure throws)
  const operatorSubject = `[leafbind contact] ${topic}: ${name}`;
  const operatorBody = [
    `New contact form submission`,
    ``,
    `Name:    ${name}`,
    `Topic:   ${topic}`,
    ``,
    `Message:`,
    `${message}`,
    ``,
    `---`,
    `Reply to this email to respond to the submitter.`,
  ].join("\n");

  await sendViaResend(
    env.RESEND_API_KEY,
    supportAddress,
    `leafbind Contact <${supportAddress}>`,
    email, // Reply-To: submitter
    operatorSubject,
    operatorBody
  );

  // 2. Auto-ack (non-blocking — failure is swallowed)
  try {
    const emailHash = await sha256Hex(email);
    const ackKey = `ack:${emailHash}`;

    const alreadyAcked = await env.CONTACT_KV.get(ackKey);
    if (!alreadyAcked) {
      const ackBody = [
        `Hi ${name},`,
        ``,
        `Thanks for reaching out. We've received your message and will`,
        `get back to you within a few business days.`,
        ``,
        `— The leafbind team`,
        ``,
        `---`,
        `You're receiving this because you submitted the contact form at leafbind.io.`,
        `No further action is needed.`,
      ].join("\n");

      await sendViaResend(
        env.RESEND_API_KEY,
        email,
        `leafbind Support <${supportAddress}>`,
        undefined,
        "We received your message — leafbind",
        ackBody
      );

      await env.CONTACT_KV.put(ackKey, "1", {
        expirationTtl: ACK_TTL_SECONDS,
      });
    }
  } catch {
    // Auto-ack failure must not surface to the submitter.
    // The operator notification already succeeded above.
    // Swallowed intentionally.
  }
}
