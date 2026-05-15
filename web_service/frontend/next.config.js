const { withPlausibleProxy } = require("next-plausible");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // NEXT_PUBLIC_API_URL is injected at build time by Vercel environment settings.
  // Set it to the Cloudflare-proxied FastAPI domain (e.g. https://api.yourdomain.com).
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001",
  },
};

// EB-252: withPlausibleProxy creates same-origin /js/script.js and /api/event
// rewrites to plausible.io. The script loads from leafbind.io instead of
// plausible.io, which bypasses ad-blockers that block third-party analytics
// hosts (uBlock, AdBlock Plus). Keeps the privacy-first guarantee — Plausible
// still receives the data via the rewrite, but the browser only sees
// leafbind.io requests in its network panel.
module.exports = withPlausibleProxy()(nextConfig);
