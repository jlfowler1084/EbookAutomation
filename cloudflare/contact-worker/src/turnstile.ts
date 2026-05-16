/**
 * EB-264: Cloudflare Turnstile server-side verification.
 *
 * Security requirements (from plan):
 * - remoteip is MANDATORY — prevents token replay across IPs within ~300s window.
 *   Pass CF-Connecting-IP header value; Cloudflare enforces single-use server-side
 *   regardless, but remoteip adds defense in depth.
 * - Fail-closed on ALL exceptions (network timeout, DNS error, parse error).
 *   A Turnstile outage blocks form submission; this is intentional.
 *   The alternative (fail-open) would disable spam protection silently.
 */

const SITEVERIFY_URL =
  "https://challenges.cloudflare.com/turnstile/v0/siteverify";

const TURNSTILE_TIMEOUT_MS = 5_000;

export async function verifyTurnstile(
  token: string,
  secret: string,
  remoteip: string
): Promise<boolean> {
  try {
    const body = new URLSearchParams({
      secret,
      response: token,
      remoteip,
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(),
      TURNSTILE_TIMEOUT_MS
    );

    let resp: Response;
    try {
      resp = await fetch(SITEVERIFY_URL, {
        method: "POST",
        body,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }

    if (!resp.ok) {
      // Non-2xx from Cloudflare — fail closed.
      // Log the status only (never the token or secret).
      console.error(
        `[contact-worker] turnstile siteverify non-2xx: status=${resp.status}`
      );
      return false;
    }

    const data = (await resp.json()) as {
      success?: boolean;
      "error-codes"?: string[];
    };
    if (data.success !== true) {
      // siteverify itself signaled rejection. error-codes is the diagnostic
      // surface ("invalid-input-response", "timeout-or-duplicate", etc.).
      // Safe to log — these codes carry no token or secret material.
      console.error(
        `[contact-worker] turnstile rejected: codes=${JSON.stringify(
          data["error-codes"] ?? []
        )}`
      );
    }
    return data.success === true;
  } catch (e) {
    // Covers: AbortError (timeout), NetworkError, SyntaxError (bad JSON).
    // All exceptions → fail closed. Log the exception name (never the value
    // of any captured variable, to avoid bleeding the token/secret).
    const name = e instanceof Error ? e.name : "Unknown";
    console.error(`[contact-worker] turnstile exception: ${name}`);
    return false;
  }
}
