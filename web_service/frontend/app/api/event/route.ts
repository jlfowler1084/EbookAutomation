// EB-252 v2: Manual proxy for Plausible event POSTs.
//
// Why this file exists: withPlausibleProxy() in next.config.js sets up
// rewrites for /js/script.js (works) and /api/event (does NOT work under
// Next.js 16 App Router — returns 404). The /api/* namespace appears to be
// intercepted by Next's file-based routing before the rewrite resolves.
//
// This route handler explicitly proxies POSTs to plausible.io/api/event,
// forwarding the request body, user-agent (for browser detection on the
// Plausible side), and the originating client IP (X-Forwarded-For — so
// Plausible attributes pageviews to user IPs, not the Vercel server IP).
//
// The proxy preserves Plausible's privacy guarantees: same-origin requests
// from the browser, no third-party plausible.io requests visible in the
// network panel, and ad-blockers that block plausible.io don't see traffic.
//
// Performance note: this runs as a Vercel serverless function (Node runtime
// by default for App Router route handlers). Plausible's response is small
// (typically empty 202 Accepted) so latency overhead vs the rewrite path is
// negligible. If volume grows past a few hundred events per minute, consider
// switching to the edge runtime (`export const runtime = "edge"`).
import { type NextRequest } from "next/server";

const PLAUSIBLE_EVENT_ENDPOINT = "https://plausible.io/api/event";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const userAgent = request.headers.get("user-agent") ?? "";
  const xForwardedFor =
    request.headers.get("x-forwarded-for") ??
    request.headers.get("x-real-ip") ??
    "";

  const upstream = await fetch(PLAUSIBLE_EVENT_ENDPOINT, {
    method: "POST",
    headers: {
      // Plausible's API accepts JSON body but historically required
      // Content-Type: text/plain to avoid CORS preflight in older browsers.
      // Both Content-Type values are accepted; we use what the Plausible
      // script itself sends to keep parity.
      "Content-Type": request.headers.get("content-type") ?? "text/plain",
      "User-Agent": userAgent,
      "X-Forwarded-For": xForwardedFor,
    },
    body,
  });

  const responseBody = await upstream.text();
  return new Response(responseBody, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "text/plain; charset=utf-8",
    },
  });
}
