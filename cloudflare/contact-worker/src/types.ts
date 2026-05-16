/**
 * EB-264: Cloudflare Worker environment bindings.
 *
 * Secrets are injected via `wrangler secret put`:
 *   - TURNSTILE_SECRET_KEY: Cloudflare Turnstile widget secret for leafbind.io
 *   - RESEND_API_KEY:        Resend REST API key (re_...) — sending-scoped
 *   - SUPPORT_INBOX_ADDRESS: support@leafbind.io (operator inbox)
 *
 * Note on SPF/DKIM alignment: outbound mail sent via Resend uses
 * send.leafbind.io as MAIL FROM. Resend signs with DKIM d=leafbind.io
 * (relaxed alignment). The apex SPF at leafbind.io is left as
 * `v=spf1 include:_spf.mx.cloudflare.net ~all` per operator decision;
 * the send.leafbind.io subdomain has its own SPF include for Resend.
 */
export interface Env {
  CONTACT_KV: KVNamespace;
  TURNSTILE_SECRET_KEY: string;
  RESEND_API_KEY: string;
  SUPPORT_INBOX_ADDRESS: string;
}

export interface ContactPayload {
  name: string;
  email: string;
  topic: string;
  message: string;
  turnstile_token: string;
  honeypot?: string;
}

export interface SanitizedPayload {
  name: string;
  email: string;
  topic: string;
  message: string;
}

export const ALLOWED_ORIGINS = [
  "https://leafbind.io",
  "https://www.leafbind.io",
];

export const CORS_HEADERS = {
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
} as const;

export const TOPIC_ALLOWLIST = [
  "general",
  "billing",
  "conversion",
  "bug",
  "feature",
] as const;

export type Topic = (typeof TOPIC_ALLOWLIST)[number];
