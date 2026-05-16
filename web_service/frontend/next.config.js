const { withPlausibleProxy } = require("next-plausible");

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // NEXT_PUBLIC_API_URL is injected at build time by Vercel environment settings.
  // Set it to the Cloudflare-proxied FastAPI domain (e.g. https://api.yourdomain.com).
  env: {
    NEXT_PUBLIC_API_URL: API_URL,
  },
  // EB-267: proxy backend-served routes through the frontend domain so that
  // same-origin forms and Stripe success_url redirects reach FastAPI instead
  // of hitting Vercel's catch-all 404.
  //   /api/recover     — RecoverClient form action (relative URL) lands here.
  //   /payment/success — Stripe success_url is hard-coded to leafbind.io in
  //                      web_service/routes/checkout.py; the page itself is
  //                      server-rendered by FastAPI per the EB-248 design.
  async rewrites() {
    return [
      { source: "/api/recover", destination: `${API_URL}/api/recover` },
      { source: "/payment/success", destination: `${API_URL}/payment/success` },
    ];
  },
};

// EB-252: withPlausibleProxy creates same-origin /js/script.js and /api/event
// rewrites to plausible.io. The script loads from leafbind.io instead of
// plausible.io, which bypasses ad-blockers that block third-party analytics
// hosts (uBlock, AdBlock Plus). Keeps the privacy-first guarantee — Plausible
// still receives the data via the rewrite, but the browser only sees
// leafbind.io requests in its network panel.
module.exports = withPlausibleProxy()(nextConfig);
