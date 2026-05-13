/** @type {import('next').NextConfig} */
const nextConfig = {
  // NEXT_PUBLIC_API_URL is injected at build time by Vercel environment settings.
  // Set it to the Cloudflare-proxied FastAPI domain (e.g. https://api.yourdomain.com).
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001",
  },
};

module.exports = nextConfig;
