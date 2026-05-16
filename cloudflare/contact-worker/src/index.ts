/**
 * EB-264: Contact form Worker on forms.leafbind.io/contact.
 *
 * Route: forms.leafbind.io/contact (all methods; Worker intercepts before origin)
 * Route binding note: forms.leafbind.io A record → 192.0.2.1 (RFC 5737 TEST-NET).
 * The Worker intercepts all traffic before the placeholder origin is consulted.
 *
 * Do NOT change this route to api.leafbind.io — that subdomain serves the
 * production FastAPI conversion backend on the Hetzner VM.
 *
 * Request flow (POST):
 *   1. CORS preflight check
 *   2. Honeypot check (field populated → 200 with fake success, no email sent)
 *   3. Parse + sanitize body
 *   4. Turnstile verification (fail-closed)
 *   5. IP rate-limit check
 *   6. Email rate-limit check
 *   7. Send operator notification + auto-ack
 *   8. Return 200 {ok: true}
 *
 * Log sanitization: never log env bindings; strip turnstile_token and email
 * from any error log before it surfaces.
 */

import type { Env, ContactPayload } from "./types.js";
import { ALLOWED_ORIGINS, CORS_HEADERS } from "./types.js";
import { sanitize } from "./sanitize.js";
import { verifyTurnstile } from "./turnstile.js";
import { checkIpLimit, checkEmailLimit } from "./rate-limit.js";
import { sendContactEmails } from "./send.js";

function corsHeaders(origin: string) {
  return {
    "Access-Control-Allow-Origin": origin,
    ...CORS_HEADERS,
  };
}

function jsonResponse(
  body: Record<string, unknown>,
  status: number,
  extraHeaders: Record<string, string> = {}
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders,
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin") ?? "";
    const isAllowedOrigin = ALLOWED_ORIGINS.includes(origin);
    const corsH = isAllowedOrigin ? corsHeaders(origin) : {};

    // OPTIONS preflight
    if (request.method === "OPTIONS") {
      if (!isAllowedOrigin) {
        return new Response(null, { status: 403 });
      }
      return new Response(null, {
        status: 204,
        headers: corsH,
      });
    }

    // Only POST accepted for the contact submission
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Parse body
    let raw: Partial<ContactPayload>;
    try {
      raw = (await request.json()) as Partial<ContactPayload>;
    } catch {
      return jsonResponse(
        { ok: false, error: "Invalid JSON body." },
        400,
        corsH
      );
    }

    // Honeypot check — return 200 with identical success body (oracle prevention)
    if (raw.honeypot) {
      return jsonResponse({ ok: true }, 200, corsH);
    }

    // Sanitize
    const sanitized = sanitize(raw);
    if (!sanitized.ok) {
      return jsonResponse(
        { ok: false, error: sanitized.error },
        sanitized.status,
        corsH
      );
    }

    // Turnstile verification
    const turnstileToken = raw.turnstile_token ?? "";
    if (!turnstileToken) {
      return jsonResponse(
        { ok: false, error: "Bot challenge token missing." },
        400,
        corsH
      );
    }

    const remoteIp =
      request.headers.get("CF-Connecting-IP") ??
      request.headers.get("X-Forwarded-For") ??
      "0.0.0.0";

    const turnstileOk = await verifyTurnstile(
      turnstileToken,
      env.TURNSTILE_SECRET_KEY,
      remoteIp
    );

    if (!turnstileOk) {
      return jsonResponse(
        { ok: false, error: "Bot challenge failed. Please refresh and try again." },
        400,
        corsH
      );
    }

    // IP rate limit
    const ipAllowed = await checkIpLimit(env.CONTACT_KV, remoteIp);
    if (!ipAllowed) {
      return jsonResponse(
        {
          ok: false,
          error:
            "Too many requests. Please wait a while before submitting again.",
        },
        429,
        { ...corsH, "Retry-After": "3600" }
      );
    }

    // Email rate limit
    const emailAllowed = await checkEmailLimit(
      env.CONTACT_KV,
      sanitized.payload.email
    );
    if (!emailAllowed) {
      return jsonResponse(
        {
          ok: false,
          error:
            "Too many submissions from this address. Please try again later.",
        },
        429,
        { ...corsH, "Retry-After": "3600" }
      );
    }

    // Send emails
    try {
      await sendContactEmails(env, sanitized.payload);
    } catch (err: unknown) {
      // Log without exposing env or email
      const message =
        err instanceof Error ? err.message : "Unknown send error";
      console.error("[contact-worker] send error:", message);

      return jsonResponse(
        {
          ok: false,
          error:
            "We couldn't deliver your message right now. Please try again in a few minutes or email support@leafbind.io directly.",
        },
        503,
        corsH
      );
    }

    return jsonResponse({ ok: true }, 200, corsH);
  },
};
